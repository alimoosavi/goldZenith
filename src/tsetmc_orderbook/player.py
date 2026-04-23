"""Interactive curses playback loop for orderbook snapshots."""

import curses
import time

from .renderer import draw_frame, init_colors


def run_curses(stdscr, snapshots, ticker, jalali_date, speed_ms):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)
    init_colors()

    idx       = 0
    paused    = False
    prev_snap = None
    last_tick = time.monotonic()

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key == ord(" "):
            paused = not paused
            last_tick = time.monotonic()
        elif key in (ord("+"), ord("=")):
            speed_ms = max(50, speed_ms // 2)
        elif key == ord("-"):
            speed_ms = min(4000, speed_ms * 2)
        elif key in (ord("r"), ord("R")):
            idx = 0
            prev_snap = None
            last_tick = time.monotonic()

        now = time.monotonic()

        if not paused and (now - last_tick) >= speed_ms / 1000:
            if idx < len(snapshots):
                draw_frame(stdscr, snapshots[idx], ticker, jalali_date,
                           idx, len(snapshots), paused, speed_ms, prev_snap)
                prev_snap = snapshots[idx]
                idx += 1
                last_tick = now
            else:
                paused = True
                draw_frame(stdscr, snapshots[-1], ticker, jalali_date,
                           idx - 1, len(snapshots), True, speed_ms, prev_snap)
        else:
            snap = snapshots[min(idx, len(snapshots) - 1)]
            draw_frame(stdscr, snap, ticker, jalali_date,
                       idx, len(snapshots), paused, speed_ms, prev_snap)


def play(snapshots, ticker, jalali_date, speed_ms):
    """Launch the curses replay. Returns when the user quits."""
    curses.wrapper(run_curses, snapshots, ticker, jalali_date, speed_ms)
