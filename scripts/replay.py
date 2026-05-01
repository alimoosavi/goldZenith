"""Replay a stored ticker-day at simulated wall-clock pace.

Loads the Parquet files persisted by `scripts/fetch_range.py` for one
`(ticker, jalali_date)` pair (filename convention
`{ticker}_{jalali}.parquet` under `ORDERBOOKS_DIR` / `TRADES_DIR`) and
walks them second-by-second, printing the prevailing best-bid /
best-ask and most recent trade on each tick.

Examples:

    uv run python scripts/replay.py --ticker 34144395039913458 --date 1405-01-11
    uv run python scripts/replay.py --ticker 34144395039913458 --date 1405-01-11 --speed 30
"""

from __future__ import annotations

import argparse

from historical import HistoricalStreamer


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", required=True, help="TSETMC instrument id")
    ap.add_argument("--date",   required=True, help="Jalali date YYYY-MM-DD")
    ap.add_argument("--speed",  type=float, default=1.0,
                    help="Replay-speed multiplier; 1.0 = wall-clock, 10 = 10× faster (default: 1.0)")
    args = ap.parse_args()

    s = HistoricalStreamer(args.ticker, args.date)
    print(f"Replaying {s.ticker} on {s.jalali_date}")
    print(f"  snapshots: {len(s.snapshots):>6}   ({s.snapshots[0].time} → {s.snapshots[-1].time})")
    print(f"  trades:    {len(s.trades):>6}")
    print(f"  speed:     {args.speed}× (sleep {1.0 / args.speed:.4f}s/tick)\n")
    s.run(speed=args.speed)


if __name__ == "__main__":
    main()
