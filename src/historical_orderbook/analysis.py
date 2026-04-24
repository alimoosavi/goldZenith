"""Cross-ticker time-series utilities derived from reconstructed orderbook snapshots."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .snapshots import seconds_to_time


def _time_to_sec(t: str) -> int:
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def snapshot_mid_price(snap: dict) -> float | None:
    """
    Mid-price at a single snapshot: (best_bid + best_ask) / 2.
    Returns None if either side has no resting orders (price == 0).
    """
    best = snap["depths"][0]
    bp, sp = best["buy_price"], best["sell_price"]
    if not bp or not sp:
        return None
    return (bp + sp) / 2


def align_mid_price_series(books: list[dict]) -> tuple[list[str], dict[str, list[float | None]]]:
    """
    Given [{ticker, snapshots}, ...], return (time_grid, mid_by_ticker).

    time_grid is a list of "HH:MM:SS" strings at 1-second resolution covering
    the union of the tickers' active windows. mid_by_ticker[ticker] is a list
    of mid-prices aligned to time_grid — None before that ticker's first
    event and after its last event; forward-filled in between.
    """
    if not books:
        return [], {}

    parsed = []
    for b in books:
        snaps = b.get("snapshots") or []
        if not snaps:
            parsed.append({"ticker": b["ticker"], "snaps": [], "first": None, "last": None})
            continue
        parsed.append({
            "ticker": b["ticker"],
            "snaps":  snaps,
            "first":  _time_to_sec(snaps[0]["time"]),
            "last":   _time_to_sec(snaps[-1]["time"]),
        })

    active = [p for p in parsed if p["first"] is not None]
    if not active:
        return [], {}

    start_sec = min(p["first"] for p in active)
    end_sec   = max(p["last"]  for p in active)

    time_grid = [seconds_to_time(s) for s in range(start_sec, end_sec + 1)]
    mid_by_ticker: dict[str, list[float | None]] = {}

    for p in parsed:
        ticker = p["ticker"]
        length = end_sec - start_sec + 1
        col: list[float | None] = [None] * length

        if p["first"] is None:
            mid_by_ticker[ticker] = col
            continue

        snaps, first, last = p["snaps"], p["first"], p["last"]
        si = 0
        last_mid = None

        for i, sec in enumerate(range(start_sec, end_sec + 1)):
            if sec < first or sec > last:
                continue
            while si < len(snaps) and _time_to_sec(snaps[si]["time"]) <= sec:
                last_mid = snapshot_mid_price(snaps[si])
                si += 1
            col[i] = last_mid

        mid_by_ticker[ticker] = col

    return time_grid, mid_by_ticker


def mid_price_dataframe(books: list[dict]) -> pd.DataFrame:
    """Return a DataFrame with a 'time' column + one column per ticker."""
    time_grid, mids = align_mid_price_series(books)
    return pd.DataFrame({"time": time_grid, **mids})


def write_mid_price_csv(books: list[dict], output_path: str | Path) -> int:
    """Write the aligned mid-price series to CSV. Returns the row count."""
    df = mid_price_dataframe(books)
    df.to_csv(output_path, index=False, float_format="%.2f")
    return len(df)
