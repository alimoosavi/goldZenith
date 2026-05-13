"""Run the orderbook persister: tail `{isin}:orderbook` Redis streams and
append every decoded snapshot to per-ISIN JSONL files for offline quant
analysis.

Examples:
    uv run python scripts/run_persister.py --broker nibi
    uv run python scripts/run_persister.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001 --out data/ticks
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from broker import BROKERS
from consumers import OrderbookPersister
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("persister")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--broker", default="nibi", choices=sorted(BROKERS.keys()),
        help="Broker whose `from_bl` decodes the BL payload (default: nibi)",
    )
    ap.add_argument(
        "--isin", action="append", default=None,
        help="ISIN to subscribe to. Repeatable. Defaults to every ISIN in config.instruments_file.",
    )
    ap.add_argument(
        "--out", type=Path, default=Path("data/ticks"),
        help="Output root directory; files land at {out}/{isin}/{date}.jsonl (default: data/ticks)",
    )
    ap.add_argument(
        "--flush-every", type=int, default=1000,
        help="Flush when buffer reaches N records (default: 1000)",
    )
    ap.add_argument(
        "--flush-interval", type=float, default=5.0,
        help="Flush when seconds since last flush ≥ this (default: 5.0)",
    )
    args = ap.parse_args()

    isins = args.isin if args.isin else [i.isin for i in InstrumentRegistry()]
    if not isins:
        sys.exit(
            f"ERROR: no ISINs to subscribe to — pass --isin or populate "
            f"{config.instruments_file}"
        )

    rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
    try:
        rm.ping()
    except Exception as exc:
        sys.exit(
            f"ERROR: cannot reach Redis at {config.redis_uri}:{config.redis_port} "
            f"— is `docker compose up -d redis` running? ({exc})"
        )

    persister = OrderbookPersister(
        broker=args.broker,
        isins=isins,
        out_dir=args.out,
        redis_manager=rm,
        flush_every=args.flush_every,
        flush_interval=args.flush_interval,
    )
    signal.signal(signal.SIGINT, lambda *_: persister.stop())

    logger.info(
        "broker=%s isins=%s → %s (flush_every=%d, flush_interval=%.1fs)",
        args.broker, isins, args.out, args.flush_every, args.flush_interval,
    )
    persister.run()
    logger.info(
        "wrote %d entries: %s", persister.written, persister.counts_by_isin,
    )


if __name__ == "__main__":
    main()
