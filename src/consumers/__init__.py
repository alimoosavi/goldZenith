"""Orderbook stream consumers.

Two implementations of the same fan-out pattern, with opposite policies:

  - `OrderbookPersister` favors durability — appends every decoded
    snapshot to per-ISIN JSONL files for offline quant analysis.
  - `ArbitrageDetector` favors latency — maintains the latest snapshot
    per ISIN and re-evaluates a pluggable strategy on every update,
    skipping the backlog on restart so stale state never fires phantom
    signals.

Both wrap `feed.OrderbookFeed`, so they share the broker-agnostic
`from_bl` decoding path and decouple via independent stream cursors —
a slow persister can't drag the arb detector down.
"""

from .arb_detector import (
    ArbitrageDetector,
    ArbSignal,
    Strategy,
    negative_spread_strategy,
)
from .persister import OrderbookPersister

__all__ = [
    "ArbSignal",
    "ArbitrageDetector",
    "OrderbookPersister",
    "Strategy",
    "negative_spread_strategy",
]