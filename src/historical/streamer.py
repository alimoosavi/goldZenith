"""Replay historical orderbook + trades second-by-second.

Loads the per-day Parquet files persisted by `storage.StorageClient`
for one `(ticker, jalali_date)` and walks them at simulated
wall-clock pace: one tick per second, each carrying the prevailing
5-depth orderbook snapshot and the most recent trade observed at or
before that second.

`HistoricalStreamer.iter_ticks()` is a pure generator — useful for
feature engineering without time.sleep — and `HistoricalStreamer.run()`
adds wall-clock pacing and prints each tick to stdout, simulating the
session unfolding live.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterator

from .orderbook import heven_to_seconds, seconds_to_time
from .schema import OrderbookSnapshot, TradeEvent

if TYPE_CHECKING:
    from storage import StorageClient


@dataclass(frozen=True, slots=True)
class StreamTick:
    """One simulated-second tick.

    `snapshot` is the per-second forward-filled book state at this
    second; `last_trade` is the most recent trade with `hEven ≤ secs`,
    or `None` if no trade has printed yet."""

    secs: int
    time: str
    snapshot: OrderbookSnapshot
    last_trade: TradeEvent | None


def _time_str_to_secs(t: str) -> int:
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def _default_format(tick: StreamTick) -> str:
    d1 = tick.snapshot.depths[0]
    bid = f"{d1.buy_price:>12,.2f} x {d1.buy_volume:<8,}"
    ask = f"{d1.sell_price:>12,.2f} x {d1.sell_volume:<8,}"
    if tick.last_trade is None:
        last = "—  no trades yet"
    else:
        lt = tick.last_trade
        last = (
            f"@{seconds_to_time(heven_to_seconds(lt.hEven))}  "
            f"vol={lt.volume:<8,} px={lt.price:,.2f}"
        )
    return f"{tick.time}  bid {bid}  │  ask {ask}  │  last {last}"


class HistoricalStreamer:
    """Walk one stored ticker-day second-by-second.

        from historical import HistoricalStreamer

        s = HistoricalStreamer("34144395039913458", "1405-01-11")
        s.run(speed=10.0)              # 10× wall-clock speed

        # or, for analysis without sleeping:
        for tick in s.iter_ticks():
            ...

    Loads the Parquet files written by `scripts/fetch_range.py` via
    `storage.StorageClient`. Inject a custom `storage` instance if you
    want to point at a non-default directory.
    """

    def __init__(
        self,
        ticker: str,
        jalali_date: str,
        *,
        storage: "StorageClient | None" = None,
    ) -> None:
        from storage import StorageClient as _SC
        store = storage or _SC()

        self.ticker = ticker
        self.jalali_date = jalali_date
        self.snapshots: list[OrderbookSnapshot] = store.load_orderbook(ticker, jalali_date)
        self.trades: list[TradeEvent] = sorted(
            store.load_trades(ticker, jalali_date),
            key=lambda t: (t.hEven, t.nTran),
        )
        if not self.snapshots:
            raise ValueError(
                f"no stored orderbook snapshots for {ticker} on {jalali_date} — "
                f"run scripts/fetch_range.py first"
            )

    # ── iteration ───────────────────────────────────────────────────────

    def iter_ticks(self) -> Iterator[StreamTick]:
        """Yield one `StreamTick` per stored snapshot, in time order.

        Snapshots are already per-second forward-filled, so they index
        seconds 1:1. The trade pointer advances monotonically, so each
        tick reflects the most recent trade observed ≤ that second.
        """
        trade_idx = 0
        last_trade: TradeEvent | None = None
        n_trades = len(self.trades)

        for snap in self.snapshots:
            secs = _time_str_to_secs(snap.time)
            while (
                trade_idx < n_trades
                and heven_to_seconds(self.trades[trade_idx].hEven) <= secs
            ):
                last_trade = self.trades[trade_idx]
                trade_idx += 1
            yield StreamTick(
                secs=secs,
                time=snap.time,
                snapshot=snap,
                last_trade=last_trade,
            )

    # ── runner ──────────────────────────────────────────────────────────

    def run(
        self,
        *,
        speed: float = 1.0,
        formatter: Callable[[StreamTick], str] | None = None,
    ) -> None:
        """Walk ticks, sleeping `1.0 / speed` seconds between each, and
        print each one through `formatter` (default: best-bid / best-ask
        + last trade). `speed=1.0` paces at the original session speed;
        `speed=10` is 10× faster.
        """
        if speed <= 0:
            raise ValueError("speed must be > 0")
        delay = 1.0 / speed
        fmt = formatter or _default_format

        for tick in self.iter_ticks():
            print(fmt(tick))
            time.sleep(delay)
