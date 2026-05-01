"""Time-of-day helpers shared by the historical pipeline.

`heven_to_seconds` decodes TSETMC's compact `HHMMSS` integer (the
`hEven` wire field) into seconds-since-midnight; `seconds_to_time`
formats those seconds back into `HH:MM:SS`. Per-second 5-depth snapshot
reconstruction lives on `historical.client.TSETMCClient`.
"""

from __future__ import annotations


def heven_to_seconds(heven: int) -> int:
    """Decode TSETMC's compact `HHMMSS` int into seconds-since-midnight.

    The hour digit can drop when it is < 10 (e.g. 84500 = 08:45:00, 5 digits;
    153000 = 15:30:00, 6 digits) — branch on length to handle both."""
    s = str(int(heven))
    if len(s) == 5:
        return int(s[0]) * 3600 + int(s[1:3]) * 60 + int(s[3:])
    return int(s[:2]) * 3600 + int(s[2:4]) * 60 + int(s[4:])


def seconds_to_time(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02}:{m:02}:{s:02}"