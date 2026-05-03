"""Parquet-backed persistence for historical orderbook + trade data.

`StorageClient` maps `(isin, jalali_date)` to one Parquet file per
stream — `{isin}_{jalali_date}.parquet` under `config.orderbooks_dir`
or `config.trades_dir`. The on-disk schema is flat and columnar so
later analytics (DuckDB, polars, etc.) can scan files directly without
going through this client.

Files are keyed by ISIN (the canonical project-wide identifier — same
key the broker streamers use as the Redis-stream prefix). Translation
to TSETMC's numeric `ins_code` happens at the CDN boundary in callers
(via `instruments.InstrumentRegistry`); this layer only sees ISIN.

Round-tripping uses the typed records from `historical.schema`:
`list[OrderbookSnapshot]` and `list[TradeEvent]` go in and come back
out unchanged. Empty inputs are still persisted with the correct
schema, so a fetched-but-empty day caches as a real file rather than
re-fetching every run.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from settings import config

from .schema import DepthLevel, OrderbookSnapshot, TradeEvent

_TRADES_SCHEMA = pa.schema([
    pa.field("nTran",    pa.int64()),
    pa.field("hEven",    pa.int32()),
    pa.field("volume",   pa.int64()),
    pa.field("price",    pa.float64()),
    pa.field("canceled", pa.int8()),
])

_ORDERBOOK_SCHEMA = pa.schema(
    [pa.field("time", pa.string())]
    + [
        pa.field(f"{side}_{kind}_{d}", pa.float64() if kind == "price" else pa.int64())
        for d in range(1, 6)
        for side, kind in (
            ("buy",  "count"),  ("buy",  "volume"),  ("buy",  "price"),
            ("sell", "price"),  ("sell", "volume"),  ("sell", "count"),
        )
    ]
)


class StorageClient:
    """Persist and load `(isin, jalali_date)` snapshots / trades as Parquet.

        store = StorageClient()
        store.save_orderbook(isin, "1405-01-11", snapshots)
        store.save_trades(isin,    "1405-01-11", trades)
        snapshots = store.load_orderbook(isin, "1405-01-11")
        trades    = store.load_trades(isin,    "1405-01-11")

    `orderbooks_dir` and `trades_dir` default to the values on
    `settings.config`; pass overrides for tests or alternate roots.
    """

    def __init__(
        self,
        *,
        orderbooks_dir: Path | None = None,
        trades_dir: Path | None = None,
        compression: str = "zstd",
    ) -> None:
        self.orderbooks_dir = Path(orderbooks_dir) if orderbooks_dir else config.orderbooks_dir
        self.trades_dir = Path(trades_dir) if trades_dir else config.trades_dir
        self.compression = compression
        self.orderbooks_dir.mkdir(parents=True, exist_ok=True)
        self.trades_dir.mkdir(parents=True, exist_ok=True)

    # ── path helpers ────────────────────────────────────────────────────

    def orderbook_path(self, isin: str, jalali_date: str) -> Path:
        return self.orderbooks_dir / f"{isin}_{jalali_date}.parquet"

    def trades_path(self, isin: str, jalali_date: str) -> Path:
        return self.trades_dir / f"{isin}_{jalali_date}.parquet"

    def has_orderbook(self, isin: str, jalali_date: str) -> bool:
        return self.orderbook_path(isin, jalali_date).is_file()

    def has_trades(self, isin: str, jalali_date: str) -> bool:
        return self.trades_path(isin, jalali_date).is_file()

    # ── trades ──────────────────────────────────────────────────────────

    def save_trades(self, isin: str, jalali_date: str, trades: list[TradeEvent]) -> Path:
        table = pa.table(
            {
                "nTran":    [t.nTran    for t in trades],
                "hEven":    [t.hEven    for t in trades],
                "volume":   [t.volume   for t in trades],
                "price":    [t.price    for t in trades],
                "canceled": [t.canceled for t in trades],
            },
            schema=_TRADES_SCHEMA,
        )
        path = self.trades_path(isin, jalali_date)
        pq.write_table(table, path, compression=self.compression)
        return path

    def load_trades(self, isin: str, jalali_date: str) -> list[TradeEvent]:
        table = pq.read_table(self.trades_path(isin, jalali_date))
        nTran    = table["nTran"].to_pylist()
        hEven    = table["hEven"].to_pylist()
        volume   = table["volume"].to_pylist()
        price    = table["price"].to_pylist()
        canceled = table["canceled"].to_pylist()
        return [
            TradeEvent(
                nTran=nTran[i], hEven=hEven[i], volume=volume[i],
                price=price[i], canceled=canceled[i],
            )
            for i in range(table.num_rows)
        ]

    # ── orderbook ───────────────────────────────────────────────────────

    def save_orderbook(
        self, isin: str, jalali_date: str, snapshots: list[OrderbookSnapshot]
    ) -> Path:
        cols: dict[str, list] = {"time": [s.time for s in snapshots]}
        for d in range(1, 6):
            cols[f"buy_count_{d}"]   = [s.depths[d - 1].buy_count   for s in snapshots]
            cols[f"buy_volume_{d}"]  = [s.depths[d - 1].buy_volume  for s in snapshots]
            cols[f"buy_price_{d}"]   = [s.depths[d - 1].buy_price   for s in snapshots]
            cols[f"sell_price_{d}"]  = [s.depths[d - 1].sell_price  for s in snapshots]
            cols[f"sell_volume_{d}"] = [s.depths[d - 1].sell_volume for s in snapshots]
            cols[f"sell_count_{d}"]  = [s.depths[d - 1].sell_count  for s in snapshots]

        table = pa.table(cols, schema=_ORDERBOOK_SCHEMA)
        path = self.orderbook_path(isin, jalali_date)
        pq.write_table(table, path, compression=self.compression)
        return path

    def load_orderbook(self, isin: str, jalali_date: str) -> list[OrderbookSnapshot]:
        return self.load_orderbook_from_path(self.orderbook_path(isin, jalali_date))

    @staticmethod
    def load_orderbook_from_path(path: Path | str) -> list[OrderbookSnapshot]:
        """Load snapshots from any Parquet file matching `_ORDERBOOK_SCHEMA`,
        regardless of filename convention. Useful for replay tooling that
        wants to point at a specific historical day on disk."""
        table = pq.read_table(Path(path))
        times = table["time"].to_pylist()
        per_depth = {
            d: {
                "buy_count":   table[f"buy_count_{d}"].to_pylist(),
                "buy_volume":  table[f"buy_volume_{d}"].to_pylist(),
                "buy_price":   table[f"buy_price_{d}"].to_pylist(),
                "sell_price":  table[f"sell_price_{d}"].to_pylist(),
                "sell_volume": table[f"sell_volume_{d}"].to_pylist(),
                "sell_count":  table[f"sell_count_{d}"].to_pylist(),
            }
            for d in range(1, 6)
        }

        snapshots: list[OrderbookSnapshot] = []
        for i, t in enumerate(times):
            depths = [
                DepthLevel(
                    depth=d,
                    buy_count=per_depth[d]["buy_count"][i],
                    buy_volume=per_depth[d]["buy_volume"][i],
                    buy_price=per_depth[d]["buy_price"][i],
                    sell_price=per_depth[d]["sell_price"][i],
                    sell_volume=per_depth[d]["sell_volume"][i],
                    sell_count=per_depth[d]["sell_count"][i],
                )
                for d in range(1, 6)
            ]
            snapshots.append(OrderbookSnapshot(time=t, depths=depths))
        return snapshots
