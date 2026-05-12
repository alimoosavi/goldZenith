"""Subscribe to `{broker}:{isin}:orderbook` Redis streams and pretty-print updates.

Two modes:

  - **real** (default): one `OrderbookFeed` consumer-only loop. Assumes a
    producer (e.g. live streamer via `task stream`, or a separate
    `task stream -- --broker <b> --mock --date <jalali>`) is already
    publishing.

        task feed -- --broker nibi --isins IRTKLOTF0001,IRTKMOFD0001

  - **mock** (`--mock --date <YYYY-MM-DD>`): spawns one mock-streamer
    background thread per ISIN, each replaying
    `{config.orderbooks_dir}/{isin}_{date}.parquet`, then runs the
    consumer loop in the main thread — one command, end-to-end demo.
    ISINs default to every entry in `config.instruments_file`; pass
    `--isins` to override. Parquets missing for the chosen date are
    skipped with a warning.

        task feed -- --broker nibi --mock --date 1403-12-01 --speed 5

Brokers are looked up from `broker.registry.BROKERS`, so `--broker
<name>` selects which streamer / mock-streamer / `from_bl` adapter the
feed uses; adding a new broker requires no changes here.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

from broker.registry import BROKERS, get_broker
from feed import BookUpdate, OrderbookFeed
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("feed")


def _format_update(u: BookUpdate) -> str:
    d1 = u.snapshot.depths[0]
    return (
        f"{u.ts}  {u.isin}  bid {d1.buy_price:>12,.2f} x {d1.buy_volume:<8,}"
        f"  │  ask {d1.sell_price:>12,.2f} x {d1.sell_volume:<8,}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--broker", default="pasargad", choices=sorted(BROKERS.keys()),
        help="Which broker's streamers + adapter to use (default: pasargad)",
    )
    ap.add_argument(
        "--isins", default="",
        help="Comma-separated ISINs (real or mock mode). "
             "If omitted, subscribes to every isin in the registry.",
    )
    ap.add_argument(
        "--mock", action="store_true",
        help="Spawn the broker's mock-streamer producers in this process "
             "(requires --date)",
    )
    ap.add_argument(
        "--date", type=str,
        help="Mock-only: Jalali date (YYYY-MM-DD) to replay; each ISIN's "
             "parquet is resolved as {config.orderbooks_dir}/{isin}_{date}.parquet",
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

    broker = get_broker(args.broker)

    if args.isins.strip():
        isins = [i.strip() for i in args.isins.split(",") if i.strip()]
    else:
        isins = [inst.isin for inst in InstrumentRegistry()]
    if not isins:
        sys.exit(
            f"ERROR: no ISINs — pass --isins or populate {config.instruments_file}"
        )

    streamers = []
    threads: list[threading.Thread] = []
    if args.mock:
        if not args.date:
            sys.exit("--mock requires --date YYYY-MM-DD")
        if broker.mock_streamer_cls is None:
            sys.exit(f"--mock: broker {args.broker!r} has no mock-streamer registered")
        spawned_isins: list[str] = []
        for isin in isins:
            try:
                s = broker.mock_streamer_cls(
                    isins=[isin], redis_manager=rm,
                    jalali_date=args.date, speed=args.speed,
                )
            except FileNotFoundError as exc:
                logger.warning("skipping %s: %s", isin, exc)
                continue
            streamers.append(s)
            t = threading.Thread(
                target=s.run, name=f"{args.broker}-mock-{isin}", daemon=True,
            )
            t.start()
            threads.append(t)
            spawned_isins.append(isin)
        if not streamers:
            sys.exit(
                f"ERROR: no parquet files found under {config.orderbooks_dir} "
                f"for date {args.date}"
            )
        isins = spawned_isins  # subscribe only to streams that actually have a producer
        logger.info(
            "mock %s: spawned %d producer thread(s) for date %s @ speed=%s×",
            args.broker, len(streamers), args.date, args.speed,
        )
    else:
        logger.info(
            "live %s: subscribing to %d stream(s): %s",
            args.broker, len(isins), ", ".join(isins),
        )

    feed = OrderbookFeed(
        broker=args.broker, isins=isins, redis_manager=rm,
        on_update=lambda u: print(_format_update(u), flush=True),
    )

    try:
        feed.run()
    except KeyboardInterrupt:
        logger.info("interrupted, stopping")
    finally:
        feed.stop()
        for s in streamers:
            s.stop()
        for t in threads:
            t.join(timeout=5)


if __name__ == "__main__":
    main()
