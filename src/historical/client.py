"""HTTP client for the TSETMC public CDN.

Fetches raw orderbook and trade history for an instrument on a given
Jalali trading day, and reconstructs them into per-second 5-depth
orderbook snapshots and clean tick-by-tick trade lists.

The base URL comes from `settings.config.tsetmc_cdn_base_url`. Endpoint
paths and the Jalali → Gregorian conversion live here so callers see a
small, single class as the public surface.
"""

from __future__ import annotations

import time
from typing import Any

import jdatetime
import requests

from settings import config

from .orderbook import heven_to_seconds, seconds_to_time
from .schema import DepthLevel, OrderbookEvent, OrderbookSnapshot, TradeEvent

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/39.0.2171.95 Safari/537.36"
    )
}


def jalali_to_gregorian_int(jalali_date: str) -> int:
    """Convert `'YYYY-MM-DD'` (Jalali) → integer `YYYYMMDD` (Gregorian) —
    the `deven` value TSETMC's CDN expects in URL paths."""
    y, m, d = jalali_date.split("-")
    g = jdatetime.date(int(y), int(m), int(d)).togregorian()
    return int(f"{g.year:04}{g.month:02}{g.day:02}")


class TSETMCClient:
    """Public CDN client wrapping orderbook (`BestLimits`) and trade-tick
    (`Trade/GetTradeHistory`) endpoints.

        client = TSETMCClient()
        snapshots = client.fetch_orderbook_snapshots("34144395039913458", "1402-03-01")
        trades    = client.fetch_trades("34144395039913458", "1402-03-01")

    `base_url` defaults to `config.tsetmc_cdn_base_url`. Transient failures
    (including the 403s the CDN occasionally returns) trigger exponential
    backoff up to `retries` total attempts.
    """

    BEST_LIMITS_PATH: str = "/api/BestLimits/{ticker}/{deven}"
    TRADE_HISTORY_PATH: str = "/api/Trade/GetTradeHistory/{ticker}/{deven}/false"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 20.0,
        retries: int = 3,
        backoff_seconds: float = 1.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or config.tsetmc_cdn_base_url).rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self._session = session or requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    # ── raw fetchers ─────────────────────────────────────────────────────

    def fetch_raw_orderbook(self, ticker: str, jalali_date: str) -> list[OrderbookEvent]:
        """Raw `bestLimitsHistory` events — one per (hEven, refID, depth)."""
        deven = jalali_to_gregorian_int(jalali_date)
        url = self.base_url + self.BEST_LIMITS_PATH.format(ticker=ticker, deven=deven)
        rows = self._get_json(url).get("bestLimitsHistory", [])
        return [
            OrderbookEvent(
                hEven=int(r["hEven"]),
                refID=int(r["refID"]),
                depth=int(r["number"]),
                buy_count=int(r["zOrdMeDem"]),
                buy_volume=int(r["qTitMeDem"]),
                buy_price=float(r["pMeDem"]),
                sell_price=float(r["pMeOf"]),
                sell_volume=int(r["qTitMeOf"]),
                sell_count=int(r["zOrdMeOf"]),
            )
            for r in rows
        ]

    def fetch_raw_trades(self, ticker: str, jalali_date: str) -> list[TradeEvent]:
        """Raw `tradeHistory` events — tick-by-tick, oldest first by `nTran`."""
        deven = jalali_to_gregorian_int(jalali_date)
        url = self.base_url + self.TRADE_HISTORY_PATH.format(ticker=ticker, deven=deven)
        rows = self._get_json(url).get("tradeHistory", [])
        return [
            TradeEvent(
                nTran=int(r["nTran"]),
                hEven=int(r["hEven"]),
                volume=int(r["qTitTran"]),
                price=float(r["pTran"]),
                canceled=int(r["canceled"]),
            )
            for r in rows
        ]

    # ── high-level helpers ───────────────────────────────────────────────

    def fetch_orderbook_snapshots(self, ticker: str, jalali_date: str) -> list[OrderbookSnapshot]:
        """Per-second 5-depth orderbook snapshots, forward-filled within the
        ticker's active trading window."""
        return self._build_snapshots(self.fetch_raw_orderbook(ticker, jalali_date))

    def fetch_trades(self, ticker: str, jalali_date: str) -> list[TradeEvent]:
        """Tick-by-tick trades as `TradeEvent` records, cancelled trades
        dropped and sorted ascending by `nTran`."""
        return self._build_trades(self.fetch_raw_trades(ticker, jalali_date))

    # ── reconstruction ───────────────────────────────────────────────────

    @staticmethod
    def _build_snapshots(events: list[OrderbookEvent]) -> list[OrderbookSnapshot]:
        """Reconstruct per-second 5-depth orderbook snapshots from raw events.

        Walks events grouped by their `(hEven, refID)` "tick" — broker-side
        sub-second ordering — applying each per-depth update to a running
        state. After every in-window tick the full 5-depth state is
        captured, then forward-filled second-by-second from
        `config.market_open` through the last in-window tick. Instruments
        that close at 12:30 naturally stop there; ETFs and funds that
        trade into the afternoon keep going.
        """
        if not events:
            return []

        sorted_events = sorted(events, key=lambda e: (e.hEven, e.refID, e.depth))

        # Latest known event per depth; None until first observed.
        state: dict[int, OrderbookEvent | None] = {d: None for d in range(1, 6)}
        ticks: list[tuple[int, dict[int, OrderbookEvent | None]]] = []

        i, n = 0, len(sorted_events)
        while i < n:
            h_even = sorted_events[i].hEven
            ref_id = sorted_events[i].refID
            while i < n and sorted_events[i].hEven == h_even and sorted_events[i].refID == ref_id:
                ev = sorted_events[i]
                state[ev.depth] = ev
                i += 1
            if config.market_open <= h_even <= config.market_close:
                ticks.append((heven_to_seconds(h_even), dict(state)))

        if not ticks:
            return []

        open_secs = heven_to_seconds(config.market_open)
        last_secs = ticks[-1][0]  # ticks ascend by hEven, so by secs too

        snapshots: list[OrderbookSnapshot] = []
        last_state: dict[int, OrderbookEvent | None] | None = None
        j = 0
        for sec in range(open_secs, last_secs + 1):
            while j < len(ticks) and ticks[j][0] <= sec:
                last_state = ticks[j][1]
                j += 1
            if last_state is None:
                continue
            depths = [
                DepthLevel(
                    depth=d,
                    buy_count=last_state[d].buy_count    if last_state[d] else 0,
                    buy_volume=last_state[d].buy_volume  if last_state[d] else 0,
                    buy_price=last_state[d].buy_price    if last_state[d] else 0.0,
                    sell_price=last_state[d].sell_price  if last_state[d] else 0.0,
                    sell_volume=last_state[d].sell_volume if last_state[d] else 0,
                    sell_count=last_state[d].sell_count  if last_state[d] else 0,
                )
                for d in range(1, 6)
            ]
            snapshots.append(OrderbookSnapshot(time=seconds_to_time(sec), depths=depths))

        return snapshots

    @staticmethod
    def _build_trades(events: list[TradeEvent]) -> list[TradeEvent]:
        """Drop cancelled trades and return the survivors sorted by `nTran`.

        Sorting ascending by `nTran` makes the result deterministically
        time-ordered even when multiple trades share the same `hEven`.
        """
        return sorted(
            (e for e in events if e.canceled == 0),
            key=lambda e: e.nTran,
        )

    # ── transport ────────────────────────────────────────────────────────

    def _get_json(self, url: str) -> dict[str, Any]:
        for attempt in range(self.retries):
            try:
                resp = self._session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException:
                if attempt + 1 == self.retries:
                    raise
                time.sleep(self.backoff_seconds * (2 ** attempt))
        raise RuntimeError("unreachable")