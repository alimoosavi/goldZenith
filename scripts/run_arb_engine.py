"""Run the arbitrage execution engine: tail `{broker}:{isin}:orderbook`
Redis streams, maintain per-ISIN orderbook state with freshness metadata,
and call `ArbExecutionEngine.evaluate(isin)` on every tick.

The base class's `evaluate` is a no-op — this runner exists to:

  - Verify the wiring (registry → engine → feed → Redis).
  - Smoke-test freshness gates against each instrument's
    `stale_threshold_seconds`.
  - Serve as the template to subclass once you have real arb logic
    (just swap `ArbExecutionEngine` here for your subclass).

Examples:
    uv run python scripts/run_arb_engine.py --broker nibi
    uv run python scripts/run_arb_engine.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001

Order placement: this runner constructs the engine without a
`NibiBrokerClient` (dry-run / detection-only). The base engine's
`evaluate` is a no-op anyway; once you subclass to place orders,
inject a `NibiBrokerClient` here.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from broker import BROKERS
from consumers import ArbExecutionEngine
from instruments import InstrumentRegistry
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("arb-engine")


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

    registry = InstrumentRegistry()
    isins = args.isin if args.isin else [i.isin for i in registry]
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

    engine = ArbExecutionEngine(
        broker=args.broker,
        isins=isins,
        registry=registry,
        redis_manager=rm,
    )
    signal.signal(signal.SIGINT, lambda *_: engine.stop())

    logger.info(
        "broker=%s isins=%d — engine running "
        "(base evaluate is a no-op; subclass to add arb logic)",
        args.broker, len(isins),
    )
    engine.run()
    logger.info("engine stopped — final state size: %d ISINs", len(engine))


if __name__ == "__main__":
    main()
