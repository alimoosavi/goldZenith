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
  - **mock** (`--mock --date <YYYY-MM-DD>`): spawns one mock-streamer
    thread per ISIN, each replaying
    `{config.orderbooks_dir}/{isin}_{date}.parquet` onto
    `{broker}:{isin}:orderbook`. ISINs default to every entry in the
    registry (`config.instruments_file`); pass `--isin` one or more
    times to replay only a subset. Parquets that don't exist for the
    chosen date are skipped with a warning.

Examples:
    docker compose up -d redis
    uv run python scripts/broker_signalr_stream.py --broker nibi
    uv run python scripts/broker_signalr_stream.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001
    uv run python scripts/broker_signalr_stream.py --broker nibi --mock \\
        --date 1403-12-01 --speed 5.0
    uv run python scripts/broker_signalr_stream.py --broker nibi --mock \\
        --date 1403-12-01 --isin IRTKMOFD0001 --speed 5.0
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

import urllib3
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(InsecureRequestWarning)

from broker import BROKERS, make_streamer
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("stream")


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
        help="Replay stored Parquets via the broker's mock-streamer instead of hitting the live hub",
    )
    ap.add_argument(
        "--date", type=str,
        help="Mock-only: Jalali date (YYYY-MM-DD) to replay; each ISIN's parquet "
             "is resolved as {config.orderbooks_dir}/{isin}_{date}.parquet",
    )
    ap.add_argument(
        "--isin", action="append", default=None,
        help="ISIN to subscribe to. Repeatable. Defaults to every ISIN in "
             "config.instruments_file in both live and mock modes.",
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
        if not args.date:
            sys.exit("--mock requires --date YYYY-MM-DD")
        isins = args.isin if args.isin else [i.isin for i in InstrumentRegistry()]
        if not isins:
            sys.exit(
                f"ERROR: no ISINs to replay — pass --isin or populate "
                f"{config.instruments_file}"
            )
        streamers = []
        for isin in isins:
            try:
                s = make_streamer(
                    broker=args.broker, isins=[isin], redis_manager=rm,
                    mock=True, jalali_date=args.date, speed=args.speed,
                )
            except FileNotFoundError as exc:
                logger.warning("skipping %s: %s", isin, exc)
                continue
            except LookupError as exc:
                sys.exit(f"ERROR: {exc}")
            streamers.append(s)
        if not streamers:
            sys.exit(
                f"ERROR: no parquet files found under {config.orderbooks_dir} "
                f"for date {args.date}"
            )
        logger.info(
            "mock %s: replaying %d isin(s) for date %s @ speed=%s× from %s",
            args.broker, len(streamers), args.date, args.speed, config.orderbooks_dir,
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
        logger.info(
            "live %s: %d isin(s) over %d connection(s) (batch_size=%d)",
            args.broker, len(isins), len(batches), batch_size,
        )
        for i, batch in enumerate(batches):
            logger.info("  conn[%d]: %s", i, batch)

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
        logger.info("interrupted, stopping all streamers")
        for s in streamers:
            s.stop()
        for t in threads:
            t.join(timeout=10)


if __name__ == "__main__":
    main()
