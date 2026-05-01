"""Fetch one ticker's orderbook snapshots and trades for a fixed Jalali day.

Edit the constants below and run:

    uv run python scripts/fetch_day.py

Prints a summary plus the first/last few entries of each stream, then
exposes `snapshots` and `trades` as module-level names so the script
can also be imported (or run with `python -i`) for quick poking.
"""

from __future__ import annotations

from historical import TSETMCClient

# ── edit these ──────────────────────────────────────────────────────────
TICKER: str = "34144395039913458"
JALALI_DATE: str = "1405-01-11"  # YYYY-MM-DD
# ────────────────────────────────────────────────────────────────────────


def _fmt_trade(t) -> str:
    return f"nTran={t.nTran:>8} hEven={t.hEven:>6} vol={t.volume:>10} price={t.price:>12,.2f}"


def _fmt_snapshot(s) -> str:
    d1 = s.depths[0]
    return (
        f"{s.time}  bid={d1.buy_price:>12,.2f} x{d1.buy_volume:<10}"
        f"  ask={d1.sell_price:>12,.2f} x{d1.sell_volume:<10}"
    )


def main() -> tuple[list, list]:
    client = TSETMCClient()

    print(f"Fetching {TICKER} on {JALALI_DATE} ...")
    snapshots = client.fetch_orderbook_snapshots(TICKER, JALALI_DATE)
    trades = client.fetch_trades(TICKER, JALALI_DATE)

    print(f"\nOrderbook snapshots: {len(snapshots)}")
    if snapshots:
        print(f"  span: {snapshots[0].time}  →  {snapshots[-1].time}")
        print("  first 3:")
        for s in snapshots[:3]:
            print("   ", _fmt_snapshot(s))
        print("  last 3:")
        for s in snapshots[-3:]:
            print("   ", _fmt_snapshot(s))

    print(f"\nTrades: {len(trades)}")
    if trades:
        print(f"  span: hEven {trades[0].hEven}  →  {trades[-1].hEven}")
        print("  first 3:")
        for t in trades[:3]:
            print("   ", _fmt_trade(t))
        print("  last 3:")
        for t in trades[-3:]:
            print("   ", _fmt_trade(t))

    return snapshots, trades


if __name__ == "__main__":
    snapshots, trades = main()
