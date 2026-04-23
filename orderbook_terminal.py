"""
orderbook_terminal.py
---------------------
Root script: fetches BestLimits history from TSETMC and replays the full
5-depth orderbook live in your terminal using curses.

Usage:
    uv run python orderbook_terminal.py
    uv run python orderbook_terminal.py --ticker 35425587644337450 --date 1402-03-01
    uv run python orderbook_terminal.py --ticker 35425587644337450 --date 1402-03-01 --speed 0.5

Controls (while running):
    q / ESC   quit
    SPACE     pause / resume
    +  / =    speed up  (halve the interval)
    -         slow down (double the interval)
    r         restart from 08:45:00
"""

import argparse
import sys
import time

from tsetmc_orderbook import build_snapshots, fetch_raw, play


def main():
    parser = argparse.ArgumentParser(description="TSETMC Terminal Orderbook Replay")
    parser.add_argument("--ticker", default="35425587644337450",
                        help="InsCode  (default: فملی)")
    parser.add_argument("--date", default="1402-03-01",
                        help="Jalali date YYYY-MM-DD  (default: 1402-03-01)")
    parser.add_argument("--speed", default=1.0, type=float,
                        help="Playback speed multiplier  (default: 1.0)")
    args = parser.parse_args()

    speed_ms = int(1000 / args.speed)

    print(f"Fetching orderbook data for {args.ticker} on {args.date} ...")
    try:
        raw = fetch_raw(args.ticker, args.date)
    except Exception as e:
        print(f"ERROR fetching data: {e}")
        sys.exit(1)

    if not raw:
        print("No data returned — check ticker/date.")
        sys.exit(1)

    print(f"Received {len(raw)} log entries. Building snapshots ...")
    snapshots = build_snapshots(raw)

    if not snapshots:
        print("No trading-hours snapshots found.")
        sys.exit(1)

    print(f"Built {len(snapshots)} per-second snapshots. Starting replay ...")
    time.sleep(0.5)

    play(snapshots, args.ticker, args.date, speed_ms)
    print("Orderbook replay ended.")


if __name__ == "__main__":
    main()
