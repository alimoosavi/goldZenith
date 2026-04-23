"""Grid dashboard: render many orderbooks at once with a shared time cursor."""

import curses
import time

from .formatting import fmt_price, fmt_vol
from .renderer import (
    C_BUY, C_BUY_BG, C_DIM, C_GOLD, C_SELL, C_SELL_BG, C_WHITE,
    init_colors,
)

# ── tile geometry ─────────────────────────────────────────────────────────────
TILE_W = 49                 # total tile width  (incl. left/right borders)
TILE_H = 11                 # total tile height (incl. top/bottom borders)
MID_COL = 24                # x-offset of the vertical bid│ask divider
TILE_GAP_X = 2
TILE_GAP_Y = 1


# ── primitives ────────────────────────────────────────────────────────────────

def _safe_addstr(stdscr, y, x, text, attr=0):
    try:
        if attr:
            stdscr.attron(attr)
        stdscr.addstr(y, x, text)
        if attr:
            stdscr.attroff(attr)
    except curses.error:
        pass


def _compute_grid(W, n):
    cols = max(1, (W + TILE_GAP_X) // (TILE_W + TILE_GAP_X))
    cols = min(cols, n)
    rows = (n + cols - 1) // cols
    return rows, cols


def _make_top(ticker, time_str):
    inner = TILE_W - 2
    title = f" ◆ {ticker}  ·  {time_str} "
    if len(title) > inner:
        title = title[:inner]
    pad = inner - len(title)
    l, r = pad // 2, pad - pad // 2
    return "╭" + "─" * l + title + "─" * r + "╮"


def _make_sep_cross():
    left  = MID_COL - 1
    right = TILE_W - MID_COL - 2
    return "├" + "─" * left + "┼" + "─" * right + "┤"


def _make_sep_tee():
    left  = MID_COL - 1
    right = TILE_W - MID_COL - 2
    return "├" + "─" * left + "┴" + "─" * right + "┤"


def _make_bottom():
    return "╰" + "─" * (TILE_W - 2) + "╯"


def _fmt_footer(best):
    if best["buy_price"] and best["sell_price"]:
        spread = best["sell_price"] - best["buy_price"]
        mid    = (best["buy_price"] + best["sell_price"]) / 2
        bps    = int(round(spread / mid * 10000)) if mid else 0
        return f"  mid {fmt_price(mid)}   spread {fmt_price(spread)} ({bps} bps)"
    return "  mid —   spread —"


# ── tile renderer ─────────────────────────────────────────────────────────────

def _draw_tile(stdscr, y, x, ticker, snap, prev_snap):
    depths  = snap["depths"]
    best    = depths[0]
    inner_w = TILE_W - 2

    dim       = curses.color_pair(C_DIM)
    gold_bold = curses.color_pair(C_GOLD) | curses.A_BOLD
    hdr_buy   = curses.color_pair(C_BUY)  | curses.A_BOLD
    hdr_sell  = curses.color_pair(C_SELL) | curses.A_BOLD

    # row 0: top border with title
    _safe_addstr(stdscr, y, x, _make_top(ticker, snap["time"]), gold_bold)

    # row 1: column header — aligned to data columns
    _safe_addstr(stdscr, y + 1, x, "│", dim)
    left_hdr  = f" {'CNT':>3}  {'VOL':>6}  {'BID':>8} "       # 23 cols
    right_hdr = f" {'ASK':<8}  {'VOL':<6}  {'CNT':<3} "       # 23 cols
    _safe_addstr(stdscr, y + 1, x + 1,            left_hdr,  hdr_buy)
    _safe_addstr(stdscr, y + 1, x + MID_COL,      "│",        dim)
    _safe_addstr(stdscr, y + 1, x + MID_COL + 1,  right_hdr, hdr_sell)
    _safe_addstr(stdscr, y + 1, x + TILE_W - 1,   "│",        dim)

    # row 2: header / body separator ├───┼───┤
    _safe_addstr(stdscr, y + 2, x, _make_sep_cross(), dim)

    # rows 3-7: 5 depth rows
    for i, d in enumerate(depths):
        row     = y + 3 + i
        is_best = (i == 0)
        base    = curses.A_BOLD if is_best else 0

        changed_bp = bool(prev_snap and
                          prev_snap["depths"][i]["buy_price"]  != d["buy_price"])
        changed_sp = bool(prev_snap and
                          prev_snap["depths"][i]["sell_price"] != d["sell_price"])

        buy_c  = curses.color_pair(C_BUY_BG  if changed_bp else C_BUY)  | base
        sell_c = curses.color_pair(C_SELL_BG if changed_sp else C_SELL) | base
        buy_d  = curses.color_pair(C_BUY)  | base
        sell_d = curses.color_pair(C_SELL) | base

        # borders + divider (divider overwritten by ▶ for best row below)
        _safe_addstr(stdscr, row, x,                  "│", dim)
        _safe_addstr(stdscr, row, x + MID_COL,        "│", dim)
        _safe_addstr(stdscr, row, x + TILE_W - 1,     "│", dim)

        # ── bid side (23 cols)
        bc = f"{d['buy_count']:>3}"
        bv = f"{fmt_vol(d['buy_volume']):>6}"
        bp = f"{fmt_price(d['buy_price']):>8}"
        left_prefix = f" {bc}  {bv}  "                        # 14 cols, up to price
        _safe_addstr(stdscr, row, x + 1,       left_prefix, buy_d)
        _safe_addstr(stdscr, row, x + 1 + 14,  bp,          buy_c)
        _safe_addstr(stdscr, row, x + 1 + 22,  " ",         buy_d)   # trailing pad

        # ── ask side (23 cols)
        sp = f"{fmt_price(d['sell_price']):<8}"
        sv = f"{fmt_vol(d['sell_volume']):<6}"
        sc = f"{d['sell_count']:<3}"
        _safe_addstr(stdscr, row, x + MID_COL + 1,       " ",  sell_d)   # leading pad
        _safe_addstr(stdscr, row, x + MID_COL + 2,       sp,   sell_c)
        right_suffix = f"  {sv}  {sc} "                       # 14 cols
        _safe_addstr(stdscr, row, x + MID_COL + 2 + 8,   right_suffix, sell_d)

        # best-depth marker overrides the middle divider
        if is_best:
            _safe_addstr(stdscr, row, x + MID_COL, "▶", gold_bold)

    # row 8: body / footer separator ├───┴───┤
    _safe_addstr(stdscr, y + 8, x, _make_sep_tee(), dim)

    # row 9: footer (mid + spread + bps)
    _safe_addstr(stdscr, y + 9, x,                "│", dim)
    footer = _fmt_footer(best)
    _safe_addstr(stdscr, y + 9, x + 1,            footer.ljust(inner_w)[:inner_w], dim)
    _safe_addstr(stdscr, y + 9, x + TILE_W - 1,   "│", dim)

    # row 10: bottom border
    _safe_addstr(stdscr, y + 10, x, _make_bottom(), dim)


# ── dashboard renderer ────────────────────────────────────────────────────────

def draw_dashboard(stdscr, books, prev_snaps, idx, max_len, speed_ms, paused, date):
    stdscr.erase()
    H, W = stdscr.getmaxyx()
    n = len(books)

    if H < TILE_H + 4 or W < TILE_W:
        _safe_addstr(stdscr, 0, 0,
                     f"Terminal too small — need at least {TILE_W}×{TILE_H + 4}")
        stdscr.refresh()
        return

    rows, cols = _compute_grid(W, n)

    # top title bar
    title = f" TSETMC DASHBOARD  ·  {date}  ·  {n} tickers "
    _safe_addstr(stdscr, 0, max(0, (W - len(title)) // 2), title[:W - 1],
                 curses.color_pair(C_GOLD) | curses.A_BOLD)

    # tile grid
    grid_w = cols * TILE_W + (cols - 1) * TILE_GAP_X
    x0 = max(0, (W - grid_w) // 2)
    y0 = 2

    for i, book in enumerate(books):
        r = i // cols
        c = i % cols
        y = y0 + r * (TILE_H + TILE_GAP_Y)
        x = x0 + c * (TILE_W + TILE_GAP_X)
        if y + TILE_H > H - 3:
            continue
        snaps = book["snapshots"]
        snap = snaps[min(idx, len(snaps) - 1)]
        _draw_tile(stdscr, y, x, book["ticker"], snap, prev_snaps[i])

    # ── bottom status bar ────────────────────────────────────────────────
    bottom = H - 2
    time_str = books[0]["snapshots"][min(idx, len(books[0]["snapshots"]) - 1)]["time"]

    open_secs  = 8 * 3600 + 45 * 60
    close_secs = 12 * 3600 + 30 * 60
    h, m, s = map(int, time_str.split(":"))
    elapsed = (h * 3600 + m * 60 + s) - open_secs
    total_t = close_secs - open_secs
    pct = max(0.0, min(1.0, elapsed / total_t))
    bar_w = max(10, W - 4)
    filled = int(pct * bar_w)

    _safe_addstr(stdscr, bottom, 2, "█" * filled, curses.color_pair(C_BUY))
    _safe_addstr(stdscr, bottom, 2 + filled, "░" * (bar_w - filled),
                 curses.color_pair(C_DIM))

    status = "⏸ PAUSED" if paused else "▶ PLAYING"
    info = f"  {time_str}  {status}  {1000/speed_ms:.1f}×  {idx+1}/{max_len}"
    _safe_addstr(stdscr, bottom + 1, 2, info,
                 curses.color_pair(C_WHITE) | curses.A_BOLD)
    hint = "    SPACE pause   +/- speed   r restart   q quit"
    _safe_addstr(stdscr, bottom + 1, 2 + len(info), hint,
                 curses.color_pair(C_DIM))

    stdscr.refresh()


# ── playback loop ─────────────────────────────────────────────────────────────

def run_dashboard(stdscr, books, date, speed_ms):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)
    init_colors()

    n = len(books)
    idx        = 0
    paused     = False
    prev_snaps = [None] * n
    last_tick  = time.monotonic()
    max_len    = max(len(b["snapshots"]) for b in books)

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
            prev_snaps = [None] * n
            last_tick = time.monotonic()

        now = time.monotonic()

        if not paused and (now - last_tick) >= speed_ms / 1000:
            if idx < max_len:
                draw_dashboard(stdscr, books, prev_snaps, idx, max_len,
                               speed_ms, paused, date)
                prev_snaps = [
                    b["snapshots"][min(idx, len(b["snapshots"]) - 1)]
                    for b in books
                ]
                idx += 1
                last_tick = now
            else:
                paused = True
                draw_dashboard(stdscr, books, prev_snaps, idx - 1, max_len,
                               speed_ms, True, date)
        else:
            draw_dashboard(stdscr, books, prev_snaps, idx, max_len,
                           speed_ms, paused, date)


def play_dashboard(books, date, speed_ms):
    """Launch the grid-dashboard curses replay. Returns when the user quits."""
    curses.wrapper(run_dashboard, books, date, speed_ms)
