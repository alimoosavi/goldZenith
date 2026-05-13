"""Arbitrage execution engine: state-holder + tick-trigger + order-placer
in a single component.

Replaces the earlier split (`OrderbookStateManager` + `ArbitrageDetector`)
with one class so the "tick arrives → update state → evaluate → maybe
place order" path is straight-line code, not a callback-through-callback
chain.

What the engine owns:

  - `self._books: dict[str, BookState]` — latest snapshot per ISIN
    with `event_ts` for freshness checks. Updated by the feed thread
    on every tick (single writer, immutable `BookState` value, atomic
    dict assignment — no locks needed; same invariants as before).
  - `self.registry: InstrumentRegistry` — for per-ISIN
    `stale_threshold_seconds` lookups via `is_fresh(isin)`.
  - `self.broker_client: NibiBrokerClient | None` — for placing /
    cancelling orders. Optional so the engine can be used in
    detection-only / dry-run mode during development.

Extension point: subclass and override `evaluate(isin: str)`. It runs
synchronously in the feed thread after `self._books[isin]` has been
updated, so the freshly-arrived snapshot is already visible via
`self.get(isin)`. Inside `evaluate`, you have access to:

  - `self.get(isin)`        — the just-updated `BookState`.
  - `self.is_fresh(isin)`   — `True` iff snapshot age <= registry threshold.
  - `self.get(other_isin)`  — other instruments' latest states (for
                              cross-instrument arb).
  - `self.registry`         — instrument metadata.
  - `self.broker_client`    — `create_order` / `cancel_order` / `get_orders`.

`evaluate` runs **inline on the feed thread**, so keep it fast —
microseconds, not milliseconds. Any I/O-heavy work (placing an order,
hitting an external API) should be punted onto a worker thread or
queue so the next tick isn't blocked. The broker client's HTTP calls
are sync `requests`, ~50–300 ms each — those will block the feed.
For production use, wrap order-placement calls in a `ThreadPoolExecutor`
or rewrite the engine on top of asyncio.

`run()` is blocking — call it from `main()` after construction. `stop()`
is thread-safe (signals the underlying `OrderbookFeed.stop()` event).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from broker.nibi import NibiBrokerClient
from feed import BookUpdate, OrderbookFeed
from historical import OrderbookSnapshot
from instruments import InstrumentRegistry
from redis_manager import RedisManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BookState:
    """One ISIN's most-recent orderbook snapshot with freshness metadata.

    `event_ts` is the broker envelope timestamp (UTC, set by the
    streamer at `XADD` time) — used by `age_seconds()` to compare
    against the instrument's `stale_threshold_seconds`.
    """

    isin: str
    snapshot: OrderbookSnapshot
    event_ts: datetime
    stream_id: str

    def age_seconds(self, now: datetime | None = None) -> float:
        """Wall-clock age of the snapshot in seconds.

        `now` defaults to `datetime.now(timezone.utc)`. Pass an explicit
        value when checking freshness across many instruments at one
        decision point — so all comparisons share a single clock
        reading and you don't see weird ordering effects from
        millisecond-scale wall-clock drift between calls.
        """
        ref = now if now is not None else datetime.now(timezone.utc)
        return (ref - self.event_ts).total_seconds()


class ArbExecutionEngine:
    """Consume orderbook streams, maintain per-ISIN state, and run
    detection + order-placement logic on every tick.

    Subclass and override `evaluate(isin)` to plug in real arb logic.
    The base implementation does nothing — useful as a working
    state-holder during development:

        class MyArb(ArbExecutionEngine):
            def evaluate(self, isin: str) -> None:
                if not self.is_fresh(isin):
                    return
                state = self.get(isin)
                # ... your arb logic; call self.broker_client.create_order(...)

    Construct, then call `run()` (blocking). `stop()` from any thread
    (e.g. SIGINT handler) signals a clean exit.
    """

    def __init__(
        self,
        broker: str,
        isins: list[str],
        *,
        registry: InstrumentRegistry,
        broker_client: NibiBrokerClient | None = None,
        redis_manager: RedisManager | None = None,
    ) -> None:
        if not isins:
            raise ValueError("ArbExecutionEngine: isins must be non-empty")
        self.broker = broker
        self.isins: list[str] = list(isins)
        self.registry = registry
        self.broker_client = broker_client
        self._books: dict[str, BookState] = {}
        self._feed = OrderbookFeed(
            broker=broker,
            isins=self.isins,
            on_update=self._on_update,
            redis_manager=redis_manager,
        )

    # ── lifecycle ────────────────────────────────────────────────────────

    def run(self) -> None:
        """Blocking — drive the feed in the calling thread. Returns
        cleanly when `stop()` is called or the feed exits."""
        logger.info(
            "execution engine starting: broker=%s isins=%d",
            self.broker, len(self.isins),
        )
        self._feed.run()
        logger.info("execution engine stopped")

    def stop(self) -> None:
        """Signal the feed to exit. Thread-safe — call from any thread
        (typically a SIGINT handler)."""
        self._feed.stop()

    # ── state queries ────────────────────────────────────────────────────

    def get(self, isin: str) -> BookState | None:
        """Return the latest `BookState` for `isin`, or `None` if no
        tick has arrived for that ISIN yet (cold start)."""
        return self._books.get(isin)

    def is_fresh(self, isin: str, *, now: datetime | None = None) -> bool:
        """Return `True` iff the latest snapshot age for `isin` is
        within the instrument's `stale_threshold_seconds`. `False`
        if no tick has arrived yet or the snapshot is too old.

        Use this as a gate before placing orders — stale state =
        bad fills."""
        state = self._books.get(isin)
        if state is None:
            return False
        inst = self.registry.by_isin(isin)
        return state.age_seconds(now) <= inst.stale_threshold_seconds

    def __contains__(self, isin: object) -> bool:
        return isinstance(isin, str) and isin in self._books

    def __len__(self) -> int:
        return len(self._books)

    # ── extension point ──────────────────────────────────────────────────

    def evaluate(self, isin: str) -> None:
        """Called on the feed thread after each tick — after
        `self._books[isin]` has been updated. Override in subclasses
        to implement arb detection + order placement.

        Default implementation is a no-op so the engine works as a
        pure state-holder for testing / development.

        Keep this fast (microseconds). For I/O-heavy work (broker
        REST calls), punt to a worker thread / queue — otherwise
        the feed thread blocks and ticks queue up in Redis."""

    # ── feed callback ────────────────────────────────────────────────────

    def _on_update(self, update: BookUpdate) -> None:
        """Wire each tick into the in-memory book, then trigger
        `evaluate(isin)`. Exceptions from `evaluate` are caught and
        logged so a buggy strategy doesn't kill the feed thread."""
        try:
            event_ts = (
                datetime.fromisoformat(update.ts)
                if update.ts else datetime.now(timezone.utc)
            )
        except ValueError:
            event_ts = datetime.now(timezone.utc)
        self._books[update.isin] = BookState(
            isin=update.isin,
            snapshot=update.snapshot,
            event_ts=event_ts,
            stream_id=update.stream_id,
        )
        try:
            self.evaluate(update.isin)
        except Exception as exc:
            logger.warning("evaluate(%s) error: %s", update.isin, exc)
