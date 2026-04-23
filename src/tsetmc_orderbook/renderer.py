"""Curses rendering of a single orderbook snapshot."""

import curses

from .formatting import fmt_price, fmt_vol

# color pair IDs
C_HEADER  = 1
C_BUY     = 2
C_SELL    = 3
C_DIM     = 4
C_GOLD    = 5
C_WHITE   = 6
C_BUY_BG  = 7
C_SELL_BG = 8
C_BAR_BUY = 9
C_BAR_SEL = 10


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HEADER,  curses.COLOR_CYAN,    -1)
    curses.init_pair(C_BUY,     curses.COLOR_GREEN,   -1)
    curses.init_pair(C_SELL,    curses.COLOR_RED,     -1)
    curses.init_pair(C_DIM,     8,                    -1)
    curses.init_pair(C_GOLD,    curses.COLOR_YELLOW,  -1)
    curses.init_pair(C_WHITE,   curses.COLOR_WHITE,   -1)
    curses.init_pair(C_BUY_BG,  curses.COLOR_BLACK,   curses.COLOR_GREEN)
    curses.init_pair(C_SELL_BG, curses.COLOR_BLACK,   curses.COLOR_RED)
    curses.init_pair(C_BAR_BUY, curses.COLOR_GREEN,   curses.COLOR_GREEN)
    curses.init_pair(C_BAR_SEL, curses.COLOR_RED,     curses.COLOR_RED)


def draw_frame(stdscr, snap, ticker, jalali_date, idx, total,
               paused, speed_ms, prev_snap):
    stdscr.erase()
    H, W = stdscr.getmaxyx()

    if H < 20 or W < 60:
        stdscr.addstr(0, 0, "Terminal too small — resize to at least 80×22")
        stdscr.refresh()
        return

    COL_CNT   = 6
    COL_VOL   = 9
    COL_PRICE = 12
    COL_DEPTH = 5
    TOTAL_W = COL_CNT + COL_VOL + COL_PRICE + COL_DEPTH + COL_PRICE + COL_VOL + COL_CNT + 6
    x0 = max(0, (W - TOTAL_W) // 2)

    row = 1

    # title bar
    title = f"  TSETMC ORDERBOOK  ·  {ticker}  ·  {jalali_date}  "
    tx = max(0, (W - len(title)) // 2)
    stdscr.attron(curses.color_pair(C_GOLD) | curses.A_BOLD)
    stdscr.addstr(row, tx, title[:W-1])
    stdscr.attroff(curses.color_pair(C_GOLD) | curses.A_BOLD)
    row += 1

    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, x0, "─" * min(TOTAL_W, W - x0 - 1))
    stdscr.attroff(curses.color_pair(C_DIM))
    row += 1

    # column headers
    def col_header(y, x, label, width, attr):
        stdscr.attron(attr)
        stdscr.addstr(y, x, label.center(width)[:width])
        stdscr.attroff(attr)

    buy_attr  = curses.color_pair(C_BUY)  | curses.A_BOLD
    sell_attr = curses.color_pair(C_SELL) | curses.A_BOLD
    dim_attr  = curses.color_pair(C_DIM)

    cx = x0
    col_header(row, cx, "ORDERS", COL_CNT,   buy_attr);  cx += COL_CNT + 1
    col_header(row, cx, "VOLUME",  COL_VOL,   buy_attr);  cx += COL_VOL + 1
    col_header(row, cx, "BID",     COL_PRICE, buy_attr);  cx += COL_PRICE + 1
    col_header(row, cx, "DEPTH",   COL_DEPTH, dim_attr);  cx += COL_DEPTH + 1
    col_header(row, cx, "ASK",     COL_PRICE, sell_attr); cx += COL_PRICE + 1
    col_header(row, cx, "VOLUME",  COL_VOL,   sell_attr); cx += COL_VOL + 1
    col_header(row, cx, "ORDERS",  COL_CNT,   sell_attr)
    row += 1

    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, x0, "─" * min(TOTAL_W, W - x0 - 1))
    stdscr.attroff(curses.color_pair(C_DIM))
    row += 1

    # depth rows
    depths = snap["depths"]
    max_bvol = max((d["buy_volume"]  for d in depths), default=1) or 1
    max_svol = max((d["sell_volume"] for d in depths), default=1) or 1

    for d in depths:
        depth = d["depth"]
        is_best = (depth == 1)

        changed_bp = changed_sp = False
        if prev_snap:
            pd_item = prev_snap["depths"][depth - 1]
            changed_bp = pd_item["buy_price"]  != d["buy_price"]
            changed_sp = pd_item["sell_price"] != d["sell_price"]

        base_attr  = curses.A_BOLD if is_best else 0
        buy_color  = curses.color_pair(C_BUY_BG  if changed_bp else C_BUY)  | base_attr
        sell_color = curses.color_pair(C_SELL_BG if changed_sp else C_SELL) | base_attr
        dim_buy    = curses.color_pair(C_BUY)
        dim_sell   = curses.color_pair(C_SELL)

        depth_label = f"  D{depth}  " if not is_best else f" ▶D{depth}◀ "
        depth_attr  = (curses.color_pair(C_GOLD) | curses.A_BOLD) if is_best \
                      else curses.color_pair(C_DIM)

        cx = x0

        bc_str = str(d["buy_count"]).rjust(COL_CNT)
        stdscr.attron(dim_buy)
        stdscr.addstr(row, cx, bc_str[:COL_CNT])
        stdscr.attroff(dim_buy)
        cx += COL_CNT + 1

        bv_str = fmt_vol(d["buy_volume"]).rjust(COL_VOL)
        stdscr.attron(dim_buy)
        stdscr.addstr(row, cx, bv_str[:COL_VOL])
        stdscr.attroff(dim_buy)
        cx += COL_VOL + 1

        bp_str  = fmt_price(d["buy_price"]).rjust(COL_PRICE)
        bar_len = int(d["buy_volume"] / max_bvol * (COL_PRICE - 2))
        stdscr.attron(curses.color_pair(C_BAR_BUY))
        stdscr.addstr(row, cx, " " * bar_len)
        stdscr.attroff(curses.color_pair(C_BAR_BUY))
        stdscr.attron(buy_color)
        stdscr.addstr(row, cx + bar_len, bp_str[bar_len:COL_PRICE])
        stdscr.attroff(buy_color)
        cx += COL_PRICE + 1

        stdscr.attron(depth_attr)
        stdscr.addstr(row, cx, depth_label[:COL_DEPTH])
        stdscr.attroff(depth_attr)
        cx += COL_DEPTH + 1

        sp_str  = fmt_price(d["sell_price"]).ljust(COL_PRICE)
        bar_len = int(d["sell_volume"] / max_svol * (COL_PRICE - 2))
        stdscr.attron(sell_color)
        stdscr.addstr(row, cx, sp_str[:COL_PRICE - bar_len])
        stdscr.attroff(sell_color)
        stdscr.attron(curses.color_pair(C_BAR_SEL))
        stdscr.addstr(row, cx + COL_PRICE - bar_len, " " * bar_len)
        stdscr.attroff(curses.color_pair(C_BAR_SEL))
        cx += COL_PRICE + 1

        sv_str = fmt_vol(d["sell_volume"]).ljust(COL_VOL)
        stdscr.attron(dim_sell)
        stdscr.addstr(row, cx, sv_str[:COL_VOL])
        stdscr.attroff(dim_sell)
        cx += COL_VOL + 1

        sc_str = str(d["sell_count"]).ljust(COL_CNT)
        stdscr.attron(dim_sell)
        stdscr.addstr(row, cx, sc_str[:COL_CNT])
        stdscr.attroff(dim_sell)

        row += 1

    # spread / mid row
    row += 1
    best = depths[0]
    if best["buy_price"] and best["sell_price"]:
        spread = best["sell_price"] - best["buy_price"]
        mid    = (best["buy_price"] + best["sell_price"]) / 2
        spread_str = f"  SPREAD: {fmt_price(spread)}   MID: {fmt_price(mid)}  "
    else:
        spread_str = "  SPREAD: —   MID: —  "

    sx = max(0, (W - len(spread_str)) // 2)
    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, sx, spread_str[:W - sx - 1])
    stdscr.attroff(curses.color_pair(C_DIM))
    row += 1

    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, x0, "─" * min(TOTAL_W, W - x0 - 1))
    stdscr.attroff(curses.color_pair(C_DIM))
    row += 1

    # time + progress
    time_str = snap["time"]
    open_secs  = 8 * 3600 + 45 * 60
    close_secs = 12 * 3600 + 30 * 60
    h, m, s = map(int, time_str.split(":"))
    elapsed = (h * 3600 + m * 60 + s) - open_secs
    total_t = close_secs - open_secs
    pct     = max(0.0, min(1.0, elapsed / total_t))
    bar_w   = min(TOTAL_W, W - x0 - 1)
    filled  = int(pct * bar_w)

    stdscr.attron(curses.color_pair(C_BUY))
    stdscr.addstr(row, x0, "█" * filled)
    stdscr.attroff(curses.color_pair(C_BUY))
    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, x0 + filled, "░" * (bar_w - filled))
    stdscr.attroff(curses.color_pair(C_DIM))
    row += 1

    status  = "  ⏸ PAUSED " if paused else "  ▶ PLAYING"
    spd_str = f"  {1000/speed_ms:.1f}×"
    snap_str = f"  {idx+1}/{total}"
    time_line = f"  {time_str}  {status}{spd_str}{snap_str}"
    open_lbl  = "  08:45"
    close_lbl = "12:30  "

    stdscr.attron(curses.color_pair(C_WHITE) | curses.A_BOLD)
    stdscr.addstr(row, x0, time_line[:W - x0 - 1])
    stdscr.attroff(curses.color_pair(C_WHITE) | curses.A_BOLD)

    row += 1
    stdscr.attron(curses.color_pair(C_DIM))
    try:
        stdscr.addstr(row, x0, open_lbl)
        stdscr.addstr(row, x0 + bar_w - len(close_lbl), close_lbl)
    except curses.error:
        pass
    stdscr.attroff(curses.color_pair(C_DIM))

    row += 1
    hint = "  SPACE pause  +/- speed  r restart  q quit"
    stdscr.attron(curses.color_pair(C_DIM))
    try:
        stdscr.addstr(row, x0, hint[:W - x0 - 1])
    except curses.error:
        pass
    stdscr.attroff(curses.color_pair(C_DIM))

    stdscr.refresh()
