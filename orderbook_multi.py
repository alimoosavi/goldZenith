"""
orderbook_multi.py
------------------
Multi-ticker orderbook replay: one Jalali date, many tickers.
Shared playback time cursor; switch active ticker with Tab / arrows.

Usage:
    uv run python orderbook_multi.py --date 1402-03-01 --tickers 35425587644337450,34144395039913458
    uv run python orderbook_multi.py --date 1402-03-01 --tickers 35425587644337450,34144395039913458 --speed 2

Controls:
    q / ESC            quit
    SPACE              pause / resume
    + / =              speed up
    -                  slow down
    r                  restart from 08:45:00
    Tab / → / n        next ticker
    Shift-Tab / ← / p  previous ticker
"""

import argparse
import sys
import time

from tsetmc_orderbook import build_snapshots, fetch_raw, play_multi


def main():
    parser = argparse.ArgumentParser(description="Multi-ticker TSETMC Orderbook Replay")
    parser.add_argument("--date", default="1402-03-01",
                        help="Jalali date YYYY-MM-DD (default: 1402-03-01)")
    parser.add_argument("--tickers", required=True,
                        help="Comma-separated InsCodes")
    parser.add_argument("--speed", default=1.0, type=float,
                        help="Playback speed multiplier (default: 1.0)")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("No tickers provided.")
        sys.exit(1)

    speed_ms = int(1000 / args.speed)

    books = []
    for t in tickers:
        print(f"Fetching {t} on {args.date} ...")
        try:
            raw = fetch_raw(t, args.date)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        if not raw:
            print(f"  {t}: no data")
            continue
        snaps = build_snapshots(raw)
        if not snaps:
            print(f"  {t}: no trading-hours snapshots")
            continue
        print(f"  {t}: {len(raw)} events → {len(snaps)} snapshots")
        books.append({"ticker": t, "date": args.date, "snapshots": snaps})

    if not books:
        print("No playable books.")
        sys.exit(1)

    print(f"\nLoaded {len(books)} book(s). Starting replay ...")
    time.sleep(0.5)

    play_multi(books, speed_ms)
    print("Orderbook replay ended.")


if __name__ == "__main__":
    main()
