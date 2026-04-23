"""Multi-ticker curses playback: one date, many orderbooks, shared time cursor."""

import curses
import time

from .renderer import draw_frame, init_colors


def run_multi_curses(stdscr, books, speed_ms):
    """
    books: list of dicts — each { 'ticker': str, 'date': str, 'snapshots': list }
    All books share a single time cursor (idx). Tab / →  next ticker,
    Shift-Tab / ←  previous ticker.
    """
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)
    init_colors()

    n = len(books)
    current   = 0
    idx       = 0
    paused    = False
    prev_snap = None
    last_tick = time.monotonic()

    max_len = max(len(b["snapshots"]) for b in books)

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
        elif key in (9, curses.KEY_RIGHT, ord("n"), ord("N")):
            current = (current + 1) % n
            prev_snap = None
        elif key in (curses.KEY_BTAB, curses.KEY_LEFT, ord("p"), ord("P")):
            current = (current - 1) % n
            prev_snap = None

        book  = books[current]
        snaps = book["snapshots"]
        label = f"[{current+1}/{n}] {book['ticker']}"

        now = time.monotonic()

        if not paused and (now - last_tick) >= speed_ms / 1000:
            if idx < max_len:
                snap = snaps[min(idx, len(snaps) - 1)]
                draw_frame(stdscr, snap, label, book["date"],
                           idx, max_len, paused, speed_ms, prev_snap)
                prev_snap = snap
                idx += 1
                last_tick = now
            else:
                paused = True
                draw_frame(stdscr, snaps[-1], label, book["date"],
                           idx - 1, max_len, True, speed_ms, prev_snap)
        else:
            snap = snaps[min(idx, len(snaps) - 1)]
            draw_frame(stdscr, snap, label, book["date"],
                       idx, max_len, paused, speed_ms, prev_snap)


def play_multi(books, speed_ms):
    """Launch the multi-ticker curses replay. Returns when the user quits."""
    curses.wrapper(run_multi_curses, books, speed_ms)
