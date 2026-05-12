"""Run a broker's streamer (real or mock) and publish to Redis.

Unified entry point — picks the streamer class from `broker.registry`
via `broker.make_streamer(...)`, so this script doesn't know or care
which broker is in play.

Two modes:

  - **live** (default): chunks the ISIN list into batches of
    `config.{broker}_instruments_per_connection` and spawns one
    streamer thread per chunk. Each streamer holds a single SignalR
    connection and multiplexes all its ISINs over it. BL events fan
    back out per-ISIN onto `{broker}:{isin}:orderbook`.
  - **mock** (`--mock --file <parquet> --isin <ISIN>`): one mock
    streamer that replays a stored historical orderbook Parquet onto
    `{broker}:{isin}:orderbook`. Only works for brokers that have
    registered a `mock_streamer_cls`.

Examples:
    docker compose up -d redis
    uv run python scripts/broker_signalr_stream.py --broker nibi
    uv run python scripts/broker_signalr_stream.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001
    uv run python scripts/broker_signalr_stream.py --broker pasargad --mock \\
        --file data/orderbooks/IRTKMOFD0001_1403-12-01.parquet \\
        --isin IRTKMOFD0001 --speed 2.0
"""

from __future__ import annotations

import argparse
import sys
import threading

import urllib3
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(InsecureRequestWarning)

from broker import BROKERS, make_streamer
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config


def _batch_size_for(broker: str) -> int:
    """Per-connection ISIN-list cap, looked up as
    `config.{broker}_instruments_per_connection`."""
    attr = f"{broker}_instruments_per_connection"
    size = getattr(config, attr, None)
    if not isinstance(size, int) or size < 1:
        sys.exit(
            f"ERROR: config.{attr} must be a positive int — add it to settings "
            f"or override via the env var {attr.upper()}"
        )
    return size


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--broker", default="pasargad", choices=sorted(BROKERS.keys()),
        help="Which broker's streamers to run (default: pasargad)",
    )
    ap.add_argument(
        "--mock", action="store_true",
        help="Replay a stored Parquet via the broker's mock-streamer instead of hitting the live hub",
    )
    ap.add_argument(
        "--file", type=str,
        help="Mock-only: path to the orderbook Parquet to replay",
    )
    ap.add_argument(
        "--isin", action="append", default=None,
        help="ISIN to subscribe to (live) or embed in the payload (mock). "
             "Repeatable in live mode; required (single value) in mock mode. "
             "Defaults to every ISIN in config.instruments_file when omitted in live mode.",
    )
    ap.add_argument(
        "--speed", type=float, default=1.0,
        help="Mock-only: replay rows-per-second multiplier (default: 1.0)",
    )
    args = ap.parse_args()

    rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
    try:
        rm.ping()
    except Exception as exc:
        sys.exit(
            f"ERROR: cannot reach Redis at {config.redis_uri}:{config.redis_port} "
            f"— is `docker compose up -d redis` running? ({exc})"
        )

    if args.mock:
        if not args.file or not args.isin or len(args.isin) != 1:
            sys.exit("--mock requires --file and exactly one --isin")
        try:
            streamers = [
                make_streamer(
                    broker=args.broker, isins=[args.isin[0]], redis_manager=rm,
                    mock=True, parquet_path=args.file, speed=args.speed,
                )
            ]
        except LookupError as exc:
            sys.exit(f"ERROR: {exc}")
        print(
            f"[mock] {args.broker}: replaying {args.file} as {args.isin[0]} "
            f"@ speed={args.speed}×",
            file=sys.stderr,
        )
    else:
        isins = args.isin if args.isin else [i.isin for i in InstrumentRegistry()]
        if not isins:
            sys.exit(
                f"ERROR: no ISINs to stream — pass --isin or populate "
                f"{config.instruments_file}"
            )
        batch_size = _batch_size_for(args.broker)
        batches = _chunks(isins, batch_size)
        streamers = [
            make_streamer(broker=args.broker, isins=batch, redis_manager=rm)
            for batch in batches
        ]
        print(
            f"[live] {args.broker}: {len(isins)} isin(s) over {len(batches)} "
            f"connection(s) (batch_size={batch_size}):",
            file=sys.stderr,
        )
        for i, batch in enumerate(batches):
            print(f"  conn[{i}]: {batch}", file=sys.stderr)

    threads = [
        threading.Thread(
            target=s.run,
            name=f"{args.broker}-{s.isins[0]}+{len(s.isins) - 1}",
            daemon=False,
        )
        for s in streamers
    ]
    for t in threads:
        t.start()
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[main] interrupted, stopping all streamers", file=sys.stderr)
        for s in streamers:
            s.stop()
        for t in threads:
            t.join(timeout=10)


if __name__ == "__main__":
    main()
