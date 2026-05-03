"""Convert unified `OrderbookSnapshot` → Pasargad BL wire format.

The unified core (see `historical.schema`) is broker-agnostic; each
broker has its own wire shape. Pasargad's BL invocation arrives as a
list of one dict, the dict carries an outer `id` + `instrumentId` and
an inner `data` array with one entry per depth level (1..5):

    [{"id": <unique>,
      "instrumentId": "IRTKMOFD0001",
      "data": [
          {"index": 1, "zOrdMeDem": ..., "qTitMeDem": ..., "pMeDem": ...,
           "zOrdMeOf": ..., "qTitMeOf": ..., "pMeOf": ...},
          ...×5,
      ]}]

`to_bl` builds exactly that shape from a unified snapshot so a
`MockPasargadStreamer` replaying historical Parquet data emits payloads
that are indistinguishable from the live broker's by structure.
"""

from __future__ import annotations

import time

from historical import DepthLevel, OrderbookSnapshot

# Pasargad wire-field renames for the depth-level dict.
_BUY_COUNT_KEY:  str = "zOrdMeDem"
_BUY_VOLUME_KEY: str = "qTitMeDem"
_BUY_PRICE_KEY:  str = "pMeDem"
_SELL_COUNT_KEY: str = "zOrdMeOf"
_SELL_VOLUME_KEY: str = "qTitMeOf"
_SELL_PRICE_KEY: str = "pMeOf"


def to_bl(snapshot: OrderbookSnapshot, isin: str) -> list[dict]:
    """Render `snapshot` as a Pasargad BL payload tagged for `isin`.

    The outer `id` is a microsecond-resolution timestamp — monotonic
    enough at our replay rates that consumers can use it as a
    deduplication / sequencing key just like they would the broker's
    own snowflake id.
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
    """Inverse of `to_bl` — decode a Pasargad BL payload back into the
    unified `OrderbookSnapshot` core type.

    `payload` is the broker's BL list (`[{id, instrumentId, data:[…×5]}]`).
    `ts_iso` is the envelope timestamp (ISO 8601 UTC, the `ts` field on
    the Redis stream entry); we extract `HH:MM:SS` for
    `OrderbookSnapshot.time` so it stays in the unified shape's HH:MM:SS
    format. Returns `(isin, snapshot)`.
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

    # ts_iso looks like "2026-05-04T12:34:56.789012+00:00"; take HH:MM:SS.
    _, _, t = ts_iso.partition("T")
    time_str = t[:8] if len(t) >= 8 else "00:00:00"

    return str(outer["instrumentId"]), OrderbookSnapshot(time=time_str, depths=depths)
