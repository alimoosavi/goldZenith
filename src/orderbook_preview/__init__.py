"""Terminal preview of reconstructed historical orderbooks.

Curses-based grid dashboard that replays one or more tickers' per-second
5-depth snapshots produced by `historical.TSETMCClient`.

    from historical import TSETMCClient
    from orderbook_preview import play_dashboard

    client = TSETMCClient()
    books = [
        {"ticker": t, "snapshots": client.fetch_orderbook_snapshots(t, date)}
        for t in tickers
    ]
    play_dashboard(books, date, speed_ms=1000)
"""

from .dashboard import play_dashboard, run_dashboard
from .formatting import fmt_price, fmt_vol

__all__ = [
    "fmt_price",
    "fmt_vol",
    "play_dashboard",
    "run_dashboard",
]