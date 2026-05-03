"""Stream live BL events from Pasargad to Redis for a fixed set of ISINs.

Each ISIN gets its own background thread + dedicated streamer instance,
publishing onto `{isin}:orderbook`. Pass `--mock` to run with the
random-data mock streamer instead — useful for offline development
without a live broker session.

Auth comes from `.env` via `settings.config` (PASARGAD_AUTH_TOKEN +
PASARGAD_COOKIE). Redis comes from `REDIS_URI` / `REDIS_PORT`.

Usage:
    docker compose up -d redis
    uv run python scripts/broker_stream.py
    uv run python scripts/broker_stream.py --mock
"""

from __future__ import annotations

import argparse
import sys
import threading

from broker.pasargad import MockPasargadStreamer, PasargadStreamer
from redis_manager import RedisManager
from settings import config

ISINS: list[str] = ["IRTKMOFD0001", "IRTKROBA0001", "IRTKZARA0001", "IRO1LTOS0001"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--mock", action="store_true",
        help="Run MockPasargadStreamer with random data instead of hitting the live hub",
    )
    ap.add_argument(
        "--tick-interval", type=float, default=0.5,
        help="Mock-only: seconds between random BL emissions (default: 0.5)",
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
        streamers = [
            MockPasargadStreamer(isin=isin, redis_manager=rm, tick_interval=args.tick_interval)
            for isin in ISINS
        ]
        print(f"[mock] spawning {len(streamers)} mock streamers @ {args.tick_interval}s ticks")
    else:
        streamers = [PasargadStreamer(isin=isin, redis_manager=rm) for isin in ISINS]
        print(f"[live] spawning {len(streamers)} Pasargad streamers")

    threads = [
        threading.Thread(target=s.run, name=f"pasargad-{s.isin}", daemon=False)
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
