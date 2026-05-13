"""Run the arbitrage execution engine: tail `{broker}:{isin}:orderbook`
Redis streams, maintain per-ISIN orderbook state with freshness metadata,
and call `ArbExecutionEngine.evaluate(isin)` on every tick.

The base class's `evaluate` is a no-op — this runner exists to:

  - Verify the wiring (registry → engine → feed → Redis).
  - Smoke-test freshness gates against each instrument's
    `stale_threshold_seconds`.
  - Serve as the template to subclass once you have real arb logic
    (just swap `ArbExecutionEngine` here for your subclass).

Pass `--watch` to render a live top-of-book dashboard for all
subscribed ISINs (full-screen ANSI redraw, freshness-coded).

Examples:
    uv run python scripts/run_arb_engine.py --broker nibi --watch
    uv run python scripts/run_arb_engine.py --broker nibi \\
        --isin IRTKMOFD0001 --isin IRTKROBA0001 --watch

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
import time
from datetime import datetime, timezone

from broker import BROKERS
from consumers import ArbExecutionEngine, BookState
from instruments import InstrumentRegistry
from orderbook_preview.formatting import fmt_price, fmt_vol
from redis_manager import RedisManager
from settings import config, setup_logging

setup_logging()
logger = logging.getLogger("arb-engine")


# ANSI control sequences for the live dashboard
_CLEAR_HOME = "\x1b[H\x1b[2J"   # move cursor to (1,1) and clear screen
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"

# Foreground colors
_GREEN  = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED    = "\x1b[31m"
_DIM    = "\x1b[2m"
_RESET  = "\x1b[0m"


class WatchEngine(ArbExecutionEngine):
    """`ArbExecutionEngine` that throttle-renders a live dashboard of
    top-of-book state per ISIN. Rendering happens inline on the feed
    thread inside `evaluate()`, capped by `render_interval` so high
    tick rates don't drown the terminal."""

    def __init__(
        self,
        *args,
        render_interval: float = 0.5,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.render_interval = render_interval
        self._last_render = 0.0

    def evaluate(self, isin: str) -> None:
        # Throttle: don't redraw on every tick — only every render_interval.
        now_mono = time.monotonic()
        if now_mono - self._last_render < self.render_interval:
            return
        self._last_render = now_mono
        self._render()

    def _render(self) -> None:
        now = datetime.now(timezone.utc)
        live_count = sum(1 for isin in self.isins if isin in self)

        lines: list[str] = []
        lines.append(
            f"{_DIM}[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}]{_RESET}  "
            f"ArbExecutionEngine — broker={self.broker}  "
            f"({live_count}/{len(self.isins)} ISINs ticking)"
        )
        lines.append("")
        lines.append(
            f"{'ISIN':14}  {'symbol':14}  {'age':>7}  "
            f"{'best bid':>18}  {'best ask':>18}  {'spread':>8}  status"
        )
        lines.append("─" * 96)

        for isin in self.isins:
            try:
                inst = self.registry.by_isin(isin)
                symbol = inst.symbol or "—"
                threshold = inst.stale_threshold_seconds
            except KeyError:
                symbol, threshold = "?", float("inf")

            state = self.get(isin)
            lines.append(_format_row(isin, symbol, threshold, state, now))

        # Single write to reduce flicker.
        sys.stdout.write(_CLEAR_HOME + "\n".join(lines) + "\n")
        sys.stdout.flush()


def _format_row(
    isin: str,
    symbol: str,
    threshold: float,
    state: BookState | None,
    now: datetime,
) -> str:
    if state is None:
        return (
            f"{isin:14}  {symbol:14}  {'—':>7}  "
            f"{'—':>18}  {'—':>18}  {'—':>8}  "
            f"{_DIM}◯ no data{_RESET}"
        )

    age = state.age_seconds(now)
    top = state.snapshot.depths[0] if state.snapshot.depths else None
    if top is None or (top.buy_price == 0 and top.sell_price == 0):
        bid = ask = spread = "—"
    else:
        bid = f"{fmt_price(top.buy_price):>10}×{fmt_vol(top.buy_volume):>6}"
        ask = f"{fmt_price(top.sell_price):>10}×{fmt_vol(top.sell_volume):>6}"
        if top.buy_price > 0 and top.sell_price > 0:
            spread_val = int(top.sell_price - top.buy_price)
            spread = f"{spread_val:,}"
        else:
            spread = "—"

    if age <= threshold:
        status = f"{_GREEN}● fresh{_RESET}"
    elif age <= 3 * threshold:
        status = f"{_YELLOW}⚠ aging{_RESET}"
    else:
        status = f"{_RED}✕ stale{_RESET}"

    return (
        f"{isin:14}  {symbol:14}  {age:>6.1f}s  "
        f"{bid:>18}  {ask:>18}  {spread:>8}  {status}"
    )


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
        "--watch", action="store_true",
        help="Render a live top-of-book dashboard for all subscribed ISINs (ANSI redraw).",
    )
    ap.add_argument(
        "--render-interval", type=float, default=0.5,
        help="With --watch: seconds between dashboard refreshes (default: 0.5).",
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

    if args.watch:
        engine = WatchEngine(
            broker=args.broker,
            isins=isins,
            registry=registry,
            redis_manager=rm,
            render_interval=args.render_interval,
        )
        sys.stdout.write(_HIDE_CURSOR)
        sys.stdout.flush()
    else:
        engine = ArbExecutionEngine(
            broker=args.broker,
            isins=isins,
            registry=registry,
            redis_manager=rm,
        )

    signal.signal(signal.SIGINT, lambda *_: engine.stop())

    logger.info(
        "broker=%s isins=%d watch=%s — engine starting "
        "(base evaluate is a no-op; subclass to add arb logic)",
        args.broker, len(isins), args.watch,
    )
    try:
        engine.run()
    finally:
        if args.watch:
            sys.stdout.write(_SHOW_CURSOR + "\n")
            sys.stdout.flush()
    logger.info("engine stopped — final state size: %d ISINs", len(engine))


if __name__ == "__main__":
    main()
