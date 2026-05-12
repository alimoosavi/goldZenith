"""Run the arbitrage detector: tail `{isin}:orderbook` Redis streams and
log signals emitted by the configured strategy. Default strategy is the
sanity-check `negative_spread_strategy` — swap in real logic by importing
the detector from `consumers` and passing `strategy=` directly.

Examples:
    uv run python scripts/run_arb_detector.py --broker nibi
    uv run python scripts/run_arb_detector.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001
"""

from __future__ import annotations

import argparse
import signal
import sys

from broker import BROKERS
from consumers import ArbitrageDetector
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config


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

    detector = ArbitrageDetector(broker=args.broker, isins=isins, redis_manager=rm)
    signal.signal(signal.SIGINT, lambda *_: detector.stop())

    print(
        f"[arb] broker={args.broker} isins={isins} watching for signals…",
        file=sys.stderr,
    )
    detector.run()


if __name__ == "__main__":
    main()
