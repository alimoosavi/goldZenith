"""
orderbook_dashboard.py
----------------------
Grid dashboard: fetches many orderbooks for one Jalali date and tiles
them all on a single screen with a shared playback clock.

Usage:
    uv run python orderbook_dashboard.py --date 1402-03-01 \\
        --tickers 35425587644337450,34144395039913458,46700660505281786

    uv run python orderbook_dashboard.py --date 1402-03-01 \\
        --tickers 35425587644337450,34144395039913458 --speed 2

Controls:
    q / ESC   quit
    SPACE     pause / resume
    + / =     speed up
    -         slow down
    r         restart from 08:45:00

Tip: make the terminal as wide as possible — tiles are 44 cols wide and
auto-arrange into a grid based on terminal size.
"""

import argparse
import sys
import time

from tsetmc_orderbook import build_snapshots, fetch_raw, play_dashboard


def main():
    parser = argparse.ArgumentParser(description="TSETMC Multi-Orderbook Grid Dashboard")
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
        books.append({"ticker": t, "snapshots": snaps})

    if not books:
        print("No playable books.")
        sys.exit(1)

    print(f"\nLoaded {len(books)} book(s). Starting dashboard ...")
    time.sleep(0.5)

    play_dashboard(books, args.date, speed_ms)
    print("Dashboard ended.")


if __name__ == "__main__":
    main()
