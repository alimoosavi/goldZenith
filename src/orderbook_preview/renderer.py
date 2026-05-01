"""Curses color-pair IDs and palette setup shared by the dashboard."""

import curses

# color pair IDs
C_HEADER  = 1
C_BUY     = 2
C_SELL    = 3
C_DIM     = 4
C_GOLD    = 5
C_WHITE   = 6
C_BUY_BG  = 7
C_SELL_BG = 8


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