"""Unified historical-market-data module for TSETMC instruments.

One `TSETMCClient` class fetches both:
  - per-second 5-depth orderbook snapshots (reconstructed from `BestLimits`
    history),
  - tick-by-tick trade history (cancelled trades filtered out).

It points at `settings.config.tsetmc_cdn_base_url` by default, retries
transient failures with exponential backoff, and decomposes the work
into raw fetchers (`fetch_raw_orderbook`, `fetch_raw_trades`) and
constructed-output helpers (`fetch_orderbook_snapshots`, `fetch_trades`).

    from historical import TSETMCClient

    client = TSETMCClient()
    snapshots = client.fetch_orderbook_snapshots("34144395039913458", "1402-03-01")
    trades    = client.fetch_trades("34144395039913458", "1402-03-01")

`HistoricalStreamer` replays a stored ticker-day second-by-second from
the local Parquet cache, yielding the prevailing orderbook snapshot and
most recent trade on each tick. Useful for "simulated time" analyses
and for feeding feature pipelines.

    from historical import HistoricalStreamer

    s = HistoricalStreamer("34144395039913458", "1402-03-01")
    for tick in s.iter_ticks():
        ...

The time-of-day utilities (`heven_to_seconds`, `seconds_to_time`) are
also re-exported for callers that want to bring their own transport.
"""

from .analysis import (
    align_mid_price_series,
    mid_price_dataframe,
    snapshot_mid_price,
    write_mid_price_csv,
)
from .client import TSETMCClient, jalali_to_gregorian_int
from .orderbook import heven_to_seconds, seconds_to_time
from .schema import (
    DepthLevel,
    OrderbookEvent,
    OrderbookSnapshot,
    TickerSnapshots,
    TradeEvent,
)
from .streamer import HistoricalStreamer, StreamTick

__all__ = [
    "DepthLevel",
    "HistoricalStreamer",
    "OrderbookEvent",
    "OrderbookSnapshot",
    "StreamTick",
    "TSETMCClient",
    "TickerSnapshots",
    "TradeEvent",
    "align_mid_price_series",
    "heven_to_seconds",
    "jalali_to_gregorian_int",
    "mid_price_dataframe",
    "seconds_to_time",
    "snapshot_mid_price",
    "write_mid_price_csv",
]
