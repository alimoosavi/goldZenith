"""Tail `{broker}:{isin}:orderbook` Redis streams and append every event to a JSONL file.

Decodes only the envelope, not the broker-specific BL payload, so it
works for any streamer registered under `broker.registry`. The key
format is owned by each broker's `orderbook_stream_key` classmethod;
this script passes `--broker` so it derives the same keys the producer
publishes to. One JSON object per line:

    {"stream": "nibi:IRTKMOFD0001:orderbook", "id": "1700000000000-0",
     "ts": "2026-05-12T08:30:01.123456+00:00", "event": "BL",
     "data": [{...broker BL payload...}]}

Examples:
    uv run python scripts/orderbook_stream_logger.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001 \\
        --out logs/orderbook.jsonl

    # Replay everything currently on the streams, then keep tailing:
    uv run python scripts/orderbook_stream_logger.py --broker nibi \\
        --isin IRTKMOFD0001 --out logs/orderbook.jsonl --from-start
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from pathlib import Path

from broker import BROKERS, get_broker
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("log-tail")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--broker", default="nibi", choices=sorted(BROKERS.keys()),
        help="Broker whose stream-key format to use (default: nibi)",
    )
    ap.add_argument(
        "--isin", action="append", default=None,
        help="ISIN to subscribe to. Repeatable. Defaults to every ISIN in config.instruments_file.",
    )
    ap.add_argument(
        "--out", type=Path, default=Path("logs/orderbook.jsonl"),
        help="File to append JSONL events to (default: logs/orderbook.jsonl)",
    )
    ap.add_argument(
        "--from-start", action="store_true",
        help="Replay every entry currently on each stream, then keep tailing. "
             "Without this flag the consumer only sees new entries (XREAD $).",
    )
    ap.add_argument(
        "--block-ms", type=int, default=1000,
        help="XREAD block timeout in ms — lower = faster Ctrl-C, higher = less Redis load (default: 1000)",
    )
    ap.add_argument(
        "--count", type=int, default=100,
        help="Max entries per XREAD response (default: 100)",
    )
    args = ap.parse_args()

    isins = args.isin if args.isin else [i.isin for i in InstrumentRegistry()]
    if not isins:
        sys.exit(
            f"ERROR: no ISINs to subscribe to — pass --isin or populate "
            f"{config.instruments_file}"
        )
    key_for = get_broker(args.broker).streamer_cls.orderbook_stream_key
    streams: dict[str, str] = {
        key_for(isin): ("0" if args.from_start else "$") for isin in isins
    }

    rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
    try:
        rm.ping()
    except Exception as exc:
        sys.exit(
            f"ERROR: cannot reach Redis at {config.redis_uri}:{config.redis_port} "
            f"— is `docker compose up -d redis` running? ({exc})"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)

    stop = False
    def _sigint(_sig, _frame):
        nonlocal stop
        stop = True
        logger.info("interrupted, stopping")
    signal.signal(signal.SIGINT, _sigint)

    logger.info(
        "streams=%s → %s (%s)",
        list(streams), args.out,
        "from-start" if args.from_start else "only-new",
    )

    written = 0
    with args.out.open("a", encoding="utf-8") as fh:
        while not stop:
            resp = rm.xread(streams, block=args.block_ms, count=args.count) or []
            for stream_key, entries in resp:
                for stream_id, fields in entries:
                    streams[stream_key] = stream_id
                    raw_data = fields.get("data")
                    try:
                        data = json.loads(raw_data) if raw_data is not None else None
                    except json.JSONDecodeError:
                        data = raw_data
                    record = {
                        "stream": stream_key,
                        "id": stream_id,
                        "ts": fields.get("ts"),
                        "event": fields.get("event"),
                        "data": data,
                    }
                    fh.write(json.dumps(record, ensure_ascii=False))
                    fh.write("\n")
                    written += 1
                fh.flush()

    logger.info("wrote %d events to %s", written, args.out)


if __name__ == "__main__":
    main()