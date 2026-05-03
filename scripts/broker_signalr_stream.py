"""Run a broker's streamer (real or mock) and publish to Redis.

Two modes:

  - **live** (default): one real streamer per ISIN in `ISINS`, each
    talking to the broker's live hub.
  - **mock** (`--mock --file <parquet> --isin <ISIN>`): one mock
    streamer that replays a stored historical orderbook Parquet onto
    `{isin}:orderbook`.

Brokers are looked up from `broker.registry.BROKERS` so `--broker
<name>` selects which streamer / mock-streamer to use.

Examples:
    docker compose up -d redis
    uv run python scripts/broker_signalr_stream.py --broker pasargad
    uv run python scripts/broker_signalr_stream.py --broker pasargad --mock \\
        --file data/orderbooks/IRTKMOFD0001_1403-12-01.parquet \\
        --isin IRTKMOFD0001 --speed 2.0
"""

from __future__ import annotations

import argparse
import sys
import threading

from broker.registry import BROKERS, get_broker
from redis_manager import RedisManager
from settings import config

ISINS: list[str] = ["IRTKMOFD0001", "IRTKROBA0001", "IRTKZARA0001", "IRTKLOTF0001"]


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
        "--isin", type=str,
        help="Mock-only: ISIN to embed in the payload + Redis-stream key prefix",
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

    if args.mock:
        if not args.file or not args.isin:
            sys.exit("--mock requires both --file and --isin")
        streamers = [
            broker.mock_streamer_cls(
                isin=args.isin, redis_manager=rm,
                parquet_path=args.file, speed=args.speed,
            )
        ]
        print(f"[mock] {args.broker}: replaying {args.file} as {args.isin} @ speed={args.speed}×")
    else:
        streamers = [broker.streamer_cls(isin=isin, redis_manager=rm) for isin in ISINS]
        print(f"[live] {args.broker}: spawning {len(streamers)} streamers")

    threads = [
        threading.Thread(target=s.run, name=f"{args.broker}-{s.isin}", daemon=False)
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
