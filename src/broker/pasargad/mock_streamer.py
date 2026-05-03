"""Mock Pasargad streamer — replays a stored historical orderbook day.

Drop-in replacement for `PasargadStreamer`: same `(isin, redis_manager)`
constructor surface, same `{isin}:orderbook` Redis-stream key, same
`emit_bl` envelope (`event=BL`, `ts=<now>`, `data=<JSON>`), same
blocking `run()` / cooperative `stop()` lifecycle. The only difference
is the data source — instead of opening a SignalR socket, this loads
one `historical.StorageClient`-format Parquet file and replays the
per-second `OrderbookSnapshot` rows through `pasargad.adapter.to_bl`,
so consumers see payloads that are structurally identical to the live
broker's.

Crucially, the `ts` field on each emitted entry is the **current**
wall-clock time — not the historical timestamp embedded in the
snapshot — so downstream arbitrage / stale-quote detectors don't fire
on replayed data the way they would if we'd used the original session
time.

`speed` controls replay pace under the assumption that each Parquet row
is one second of session time:
  - `speed=1.0` → 1 row/sec (real-time replay).
  - `speed=2.0` → 2 rows/sec (sleep 0.5s between rows).
  - `speed=0.5` → 1 row every 2 sec.
"""

from __future__ import annotations

import threading
from pathlib import Path

from historical import StorageClient
from redis_manager import RedisManager

from .adapter import to_bl
from ..base_streamer import BaseStreamer


class MockPasargadStreamer(BaseStreamer):
    """Replay a stored orderbook day onto the same Redis stream a real
    `PasargadStreamer` would publish to.

        from redis_manager import RedisManager
        from broker.pasargad import MockPasargadStreamer
        from settings import config

        rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
        MockPasargadStreamer(
            isin="IRTKMOFD0001",
            redis_manager=rm,
            parquet_path="data/orderbooks/IRTKMOFD0001_1403-12-01.parquet",
            speed=2.0,
        ).run()
    """

    def __init__(
        self,
        *,
        isin: str,
        redis_manager: RedisManager,
        parquet_path: Path | str,
        speed: float = 1.0,
        stream_maxlen: int | None = 10_000,
    ) -> None:
        super().__init__(isin=isin, redis_manager=redis_manager, stream_maxlen=stream_maxlen)
        if speed <= 0:
            raise ValueError("MockPasargadStreamer: speed must be > 0")
        self.parquet_path = Path(parquet_path)
        if not self.parquet_path.is_file():
            raise FileNotFoundError(
                f"MockPasargadStreamer: parquet file not found: {self.parquet_path}"
            )
        self.speed = speed
        self._stop = threading.Event()

    def run(self) -> None:
        """Blocking. Loads the parquet, then emits one BL payload per row
        at `1.0/speed` second cadence until `stop()` is called or the file
        is exhausted."""
        snapshots = StorageClient.load_orderbook_from_path(self.parquet_path)
        if not snapshots:
            self._log("mock", f"{self.parquet_path.name} has no rows, nothing to replay")
            return

        delay = 1.0 / self.speed
        self._log(
            "mock",
            f"replaying {len(snapshots)} rows from {self.parquet_path.name} "
            f"@ speed={self.speed}× → {self.orderbook_stream_key}",
        )

        self._stop.clear()
        for snap in snapshots:
            if self._stop.is_set():
                break
            payload = to_bl(snap, self.isin)
            try:
                self.emit_bl(payload)
            except Exception as exc:
                self._log("emit_bl error", str(exc))
            if self._stop.wait(delay):
                break

        self._log("mock", "replay finished")

    def stop(self) -> None:
        self._stop.set()
