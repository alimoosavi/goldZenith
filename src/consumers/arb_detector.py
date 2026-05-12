"""Detect arbitrage signals across orderbook streams.

Maintains the latest `OrderbookSnapshot` per ISIN and re-evaluates a
pluggable `Strategy` callback on every update. The strategy is the
extension point — pass `strategy=` to inject real cross-instrument
logic (ETF vs basket, futures vs spot, etc.); the default
`negative_spread_strategy` is a sanity-check stub that flags any
orderbook whose top-of-book buy price exceeds the top sell price.

Latency-first design:

  - Subscribes via `OrderbookFeed` with the default `last_ids="$"`, so
    on restart the detector skips the backlog and re-anchors to the
    current top of book. Stale orderbook is useless signal, and
    replaying it would generate phantom alerts.
  - `on_signal` runs inline from the `XREAD` thread — keep it cheap
    (publish to a Redis pub/sub channel, append to a log, push to a
    metric) and offload heavy work to a separate worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from feed import BookUpdate, OrderbookFeed
from historical import OrderbookSnapshot
from redis_manager import RedisManager


@dataclass(frozen=True, slots=True)
class ArbSignal:
    """One detected arbitrage opportunity.

    `kind` is a short human-readable label (`"negative_spread"`,
    `"etf_basket_diverged"`, ...); `details` is a strategy-specific
    structured payload, e.g. prices, sizes, expected edge.
    """

    isin: str
    ts: str
    kind: str
    details: dict = field(default_factory=dict)


Strategy = Callable[[BookUpdate, dict[str, OrderbookSnapshot]], list[ArbSignal]]


def negative_spread_strategy(
    update: BookUpdate,
    _books: dict[str, OrderbookSnapshot],
) -> list[ArbSignal]:
    """Flag any orderbook whose top buy_price exceeds top sell_price.

    A well-formed book never satisfies this — it's a sanity-check stub
    so the detector emits something observable end-to-end. Replace with
    real cross-instrument logic once you know what edge you want to
    trade.
    """
    if not update.snapshot.depths:
        return []
    top = update.snapshot.depths[0]
    if top.buy_price > 0 and top.sell_price > 0 and top.buy_price > top.sell_price:
        return [
            ArbSignal(
                isin=update.isin,
                ts=update.ts,
                kind="negative_spread",
                details={
                    "buy_price": top.buy_price,
                    "sell_price": top.sell_price,
                    "edge": top.buy_price - top.sell_price,
                },
            )
        ]
    return []


class ArbitrageDetector:
    """Tail orderbook streams across N instruments and emit signals via a
    pluggable strategy callback."""

    def __init__(
        self,
        broker: str,
        isins: list[str],
        *,
        strategy: Strategy = negative_spread_strategy,
        on_signal: Callable[[ArbSignal], None] | None = None,
        redis_manager: RedisManager | None = None,
    ) -> None:
        self.strategy = strategy
        self.on_signal = on_signal or _default_on_signal
        self.books: dict[str, OrderbookSnapshot] = {}
        self.feed = OrderbookFeed(
            broker=broker,
            isins=isins,
            on_update=self._on_update,
            redis_manager=redis_manager,
        )

    def run(self) -> None:
        self.feed.run()

    def stop(self) -> None:
        self.feed.stop()

    def _on_update(self, update: BookUpdate) -> None:
        self.books[update.isin] = update.snapshot
        try:
            signals = self.strategy(update, self.books)
        except Exception as exc:
            print(f"[ArbitrageDetector] strategy error on {update.isin}: {exc}")
            return
        for sig in signals:
            try:
                self.on_signal(sig)
            except Exception as exc:
                print(f"[ArbitrageDetector] on_signal error: {exc}")


def _default_on_signal(sig: ArbSignal) -> None:
    print(f"[arb] {sig.ts} {sig.isin} {sig.kind} {sig.details}")
