"""Reconstruct per-second 5-depth orderbook snapshots from raw BestLimits history."""

import pandas as pd

MARKET_OPEN = 84500    # 08:45:00
MARKET_CLOSE = 123000  # 12:30:00

DEPTH_COLS = [
    "buy_count", "buy_volume", "buy_price",
    "sell_price", "sell_volume", "sell_count",
]


def heven_to_seconds(heven: int) -> int:
    s = str(int(heven))
    if len(s) == 5:
        return int(s[0]) * 3600 + int(s[1:3]) * 60 + int(s[3:])
    return int(s[:2]) * 3600 + int(s[2:4]) * 60 + int(s[4:])


def seconds_to_time(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02}:{m:02}:{s:02}"


def build_snapshots(raw: list) -> list:
    """
    Returns a list of per-second dicts covering 08:45:00 → 12:30:00.
    Each dict: { 'time': 'HH:MM:SS', 'depths': [ {depth,buy_*,sell_*}, ... ] }
    Forward-filled so every second has a complete 5-depth book state.
    """
    rows = []
    for e in raw:
        rows.append({
            "hEven":       int(e["hEven"]),
            "refID":       int(e["refID"]),
            "depth":       int(e["number"]),
            "buy_count":   e["zOrdMeDem"],
            "buy_volume":  e["qTitMeDem"],
            "buy_price":   e["pMeDem"],
            "sell_price":  e["pMeOf"],
            "sell_volume": e["qTitMeOf"],
            "sell_count":  e["zOrdMeOf"],
        })

    df = pd.DataFrame(rows).sort_values(["hEven", "refID", "depth"]).reset_index(drop=True)

    wide = df.pivot_table(
        index=["hEven", "refID"],
        columns="depth",
        values=DEPTH_COLS,
        aggfunc="first",
    )
    wide.columns = [f"{col}_{d}" for col, d in wide.columns]
    wide = wide.reset_index().sort_values(["hEven", "refID"]).reset_index(drop=True)

    val_cols = [c for c in wide.columns if any(c.endswith(f"_{i}") for i in range(1, 6))]
    wide[val_cols] = wide[val_cols].ffill()

    wide = wide[(wide["hEven"] >= MARKET_OPEN) & (wide["hEven"] <= MARKET_CLOSE)]
    wide["secs"] = wide["hEven"].apply(heven_to_seconds)

    open_secs = heven_to_seconds(MARKET_OPEN)
    close_secs = heven_to_seconds(MARKET_CLOSE)

    snapshots = []
    for sec in range(open_secs, close_secs + 1):
        mask = wide["secs"] <= sec
        if not mask.any():
            continue
        row = wide.loc[mask[::-1].idxmax()]

        depths = []
        for d in range(1, 6):
            depths.append({
                "depth":       d,
                "buy_count":   int(row.get(f"buy_count_{d}",   0) or 0),
                "buy_volume":  int(row.get(f"buy_volume_{d}",  0) or 0),
                "buy_price":   float(row.get(f"buy_price_{d}",   0) or 0),
                "sell_price":  float(row.get(f"sell_price_{d}",  0) or 0),
                "sell_volume": int(row.get(f"sell_volume_{d}", 0) or 0),
                "sell_count":  int(row.get(f"sell_count_{d}",  0) or 0),
            })
        snapshots.append({"time": seconds_to_time(sec), "depths": depths})

    return snapshots
