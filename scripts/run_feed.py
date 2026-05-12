"""Subscribe to `{isin}:orderbook` Redis streams and pretty-print updates.

Two modes:

  - **real** (default): one `OrderbookFeed` consumer-only loop. Assumes a
    producer (e.g. live `PasargadStreamer` via `task stream`, or a
    separate `task stream -- --mock ...`) is already publishing.

        task feed -- --broker pasargad --isins IRTKLOTF0001,IRTKMOFD0001

  - **mock** (`--mock`): spawns the broker's mock-streamer as a
    background thread per (isin, parquet) pair, then runs the same
    consumer loop in the main thread — one command, end-to-end demo.

        task feed -- --broker pasargad --mock \\
            --mock-file IRTKLOTF0001=data/orderbooks/IRTKLOTF0001_1403-12-01.parquet \\
            --mock-file IRTKMOFD0001=data/orderbooks/IRTKMOFD0001_1403-12-02.parquet \\
            --speed 5

Brokers are looked up from `broker.registry.BROKERS`, so `--broker
<name>` selects which streamer / mock-streamer / `from_bl` adapter the
feed uses; adding a new broker requires no changes here.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from broker.registry import BROKERS, get_broker
from feed import BookUpdate, OrderbookFeed
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("feed")


def _parse_mock_files(specs: list[str]) -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    for spec in specs:
        isin, sep, path = spec.partition("=")
        if not sep or not isin or not path:
            sys.exit(f"--mock-file must be ISIN=PATH, got: {spec!r}")
        p = Path(path)
        if not p.is_file():
            sys.exit(f"--mock-file {isin}: file not found: {p}")
        pairs.append((isin, p))
    return pairs


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
        help="Real-mode: comma-separated ISINs to subscribe to. "
             "If omitted, subscribes to every isin in the registry.",
    )
    ap.add_argument(
        "--mock", action="store_true",
        help="Spawn the broker's mock-streamer producers in this process "
             "(requires --mock-file pairs)",
    )
    ap.add_argument(
        "--mock-file", action="append", default=[], metavar="ISIN=PATH",
        help="Mock-only: one (ISIN, parquet) pair; repeat for multiple instruments",
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

    streamers = []
    threads: list[threading.Thread] = []
    if args.mock:
        pairs = _parse_mock_files(args.mock_file)
        if not pairs:
            sys.exit("--mock requires at least one --mock-file ISIN=PATH")
        isins = [isin for isin, _ in pairs]
        for isin, path in pairs:
            s = broker.mock_streamer_cls(
                isins=[isin], redis_manager=rm,
                parquet_path=path, speed=args.speed,
            )
            streamers.append(s)
            t = threading.Thread(
                target=s.run, name=f"{args.broker}-mock-{isin}", daemon=True,
            )
            t.start()
            threads.append(t)
        logger.info(
            "mock %s: spawned %d producer thread(s) @ speed=%s×",
            args.broker, len(streamers), args.speed,
        )
    else:
        if args.isins.strip():
            isins = [i.strip() for i in args.isins.split(",") if i.strip()]
        else:
            isins = [inst.isin for inst in InstrumentRegistry()]
        if not isins:
            sys.exit("real-mode: --isins is empty and the registry has no entries")
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
