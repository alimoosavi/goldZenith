"""Convert unified `OrderbookSnapshot` ↔ Nibi BL wire format.

Nibi's BL wire shape is identical to Pasargad's (same outer envelope
+ same Persian-abbreviation depth-level keys), so this module is a
verbatim clone of `broker.pasargad.adapter`. Kept as its own file
rather than re-exported so Nibi can diverge later without churning
Pasargad.

Outer envelope:

    [{"id": <unique>,
      "instrumentId": "IRTKMOFD0001",
      "data": [
          {"index": 1, "zOrdMeDem": ..., "qTitMeDem": ..., "pMeDem": ...,
           "zOrdMeOf": ..., "qTitMeOf": ..., "pMeOf": ...},
          ...×5,
      ]}]
"""

from __future__ import annotations

import time

from historical import DepthLevel, OrderbookSnapshot

_BUY_COUNT_KEY:  str = "zOrdMeDem"
_BUY_VOLUME_KEY: str = "qTitMeDem"
_BUY_PRICE_KEY:  str = "pMeDem"
_SELL_COUNT_KEY: str = "zOrdMeOf"
_SELL_VOLUME_KEY: str = "qTitMeOf"
_SELL_PRICE_KEY: str = "pMeOf"


def to_bl(snapshot: OrderbookSnapshot, isin: str) -> list[dict]:
    """Render `snapshot` as a Nibi BL payload tagged for `isin`.

    The outer `id` is a microsecond-resolution Unix timestamp —
    monotonic enough at replay rates that consumers can use it as a
    dedup / sequencing key just like the broker's own id.
    """
    depths = [
        {
            "index":           level.depth,
            _BUY_COUNT_KEY:    level.buy_count,
            _BUY_VOLUME_KEY:   level.buy_volume,
            _BUY_PRICE_KEY:    level.buy_price,
            _SELL_COUNT_KEY:   level.sell_count,
            _SELL_VOLUME_KEY:  level.sell_volume,
            _SELL_PRICE_KEY:   level.sell_price,
        }
        for level in snapshot.depths
    ]
    return [
        {
            "id":           int(time.time() * 1_000_000),
            "instrumentId": isin,
            "data":         depths,
        }
    ]


def from_bl(payload: list[dict], ts_iso: str) -> tuple[str, OrderbookSnapshot]:
    """Inverse of `to_bl` — decode a Nibi BL payload into the unified
    `OrderbookSnapshot`. `ts_iso` is the envelope timestamp on the
    Redis stream entry; the HH:MM:SS slice is used for
    `OrderbookSnapshot.time`. Returns `(isin, snapshot)`.
    """
    if not payload:
        raise ValueError("from_bl: empty payload")
    outer = payload[0]
    rows = outer.get("data") or []
    if not rows:
        raise ValueError("from_bl: payload[0]['data'] is empty")

    depths = [
        DepthLevel(
            depth=int(d["index"]),
            buy_count=int(d[_BUY_COUNT_KEY]),
            buy_volume=int(d[_BUY_VOLUME_KEY]),
            buy_price=float(d[_BUY_PRICE_KEY]),
            sell_price=float(d[_SELL_PRICE_KEY]),
            sell_volume=int(d[_SELL_VOLUME_KEY]),
            sell_count=int(d[_SELL_COUNT_KEY]),
        )
        for d in rows
    ]
    depths.sort(key=lambda x: x.depth)

    _, _, t = ts_iso.partition("T")
    time_str = t[:8] if len(t) >= 8 else "00:00:00"

    return str(outer["instrumentId"]), OrderbookSnapshot(time=time_str, depths=depths)
