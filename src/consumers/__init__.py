"""Orderbook stream consumers.

Three roles built on the same `feed.OrderbookFeed` fan-out:

  - `OrderbookPersister` favors durability — appends every decoded
    snapshot to per-ISIN JSONL files for offline quant analysis.
  - `ArbExecutionEngine` is the unified arbitrage component: maintains
    per-ISIN `BookState` in memory, runs detection logic on every tick
    via the overridable `evaluate(isin)` hook, and places orders via
    an injected `NibiBrokerClient`. Subclass it to plug in real arb
    logic.
  - `ArbitrageDetector` is the legacy detector-only class (no order
    placement, callback-based strategy). Kept for now as a working
    reference; new code should build on `ArbExecutionEngine`.

All three wrap `feed.OrderbookFeed`, share the broker-agnostic
`from_bl` decoding path, and decouple via independent stream cursors —
a slow persister can't drag the execution engine down.
"""

from .arb_detector import (
    ArbitrageDetector,
    ArbSignal,
    Strategy,
    negative_spread_strategy,
)
from .execution_engine import ArbExecutionEngine, BookState
from .persister import OrderbookPersister

__all__ = [
    "ArbExecutionEngine",
    "ArbSignal",
    "ArbitrageDetector",
    "BookState",
    "OrderbookPersister",
    "Strategy",
    "negative_spread_strategy",
]