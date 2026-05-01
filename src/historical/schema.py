"""Typed records for the TSETMC historical-data pipeline.

Two layers of records live here:

  - **Wire-format events** (`OrderbookEvent`, `TradeEvent`) — one entry per
    row of a CDN endpoint, after the cryptic `qTitTran`/`pMeDem`/etc.
    keys have been renamed and stripped of noise fields. Produced by
    `historical.client.TSETMCClient` raw fetchers.

  - **Constructed records** (`DepthLevel`, `OrderbookSnapshot`,
    `TickerSnapshots`) — higher-level shapes emitted by
    `TSETMCClient.fetch_orderbook_snapshots` and the analysis layer.
    Each replaces a `dict[str, Any]` shape with a typed,
    attribute-accessed dataclass.

All records are `frozen=True, slots=True`:
  - frozen → immutable + hashable, safe to share across threads.
  - slots  → faster attribute access, lower memory; sessions can hold
    millions of these.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── wire-format events ──────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class OrderbookEvent:
    """One level-update event from TSETMC's `bestLimitsHistory`.

    A single event reports the state of one depth level (1..5) on both
    sides of the book at the given `hEven` timestamp. Multiple events
    can share an `hEven`; `refID` provides the broker-side intra-second
    ordering. The full 5-depth book state at a given second is rebuilt
    by `historical.client.TSETMCClient.fetch_orderbook_snapshots`.
    """

    hEven: int           # HHMMSS-packed time of day
    refID: int           # broker-side update id (sub-second tiebreak)
    depth: int           # depth level, 1..5
    buy_count: int
    buy_volume: int
    buy_price: float
    sell_price: float
    sell_volume: int
    sell_count: int


@dataclass(frozen=True, slots=True)
class TradeEvent:
    """One trade tick from TSETMC's `tradeHistory`.

    Multiple trades can share an `hEven`; `nTran` provides a strict
    intraday ordering (oldest first). `canceled != 0` marks a trade
    that was voided after execution — `TSETMCClient.fetch_trades`
    drops these rows.
    """

    nTran: int           # intraday sequence number
    hEven: int           # HHMMSS-packed time of day
    volume: int          # qTitTran — number of shares
    price: float         # pTran — execution price
    canceled: int        # 0 = valid trade, != 0 = cancelled / voided


# ── reconstructed orderbook records ─────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class DepthLevel:
    """One row of a 5-depth snapshot. Carries both the bid and ask side at
    `depth` (1..5)."""

    depth: int           # 1..5
    buy_count: int
    buy_volume: int
    buy_price: float
    sell_price: float
    sell_volume: int
    sell_count: int


@dataclass(frozen=True, slots=True)
class OrderbookSnapshot:
    """A full 5-depth orderbook state at one second of the trading day —
    the per-second forward-filled output of
    `TSETMCClient.fetch_orderbook_snapshots`. `depths` is always
    length-5 ordered by `depth=1..5`."""

    time: str                     # HH:MM:SS
    depths: list[DepthLevel]


@dataclass(frozen=True, slots=True)
class TickerSnapshots:
    """Pairs a ticker id with its reconstructed snapshot timeline; consumed
    by the analysis utilities and the curses preview dashboard."""

    ticker: str
    snapshots: list[OrderbookSnapshot]
