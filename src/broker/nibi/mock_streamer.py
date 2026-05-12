"""Mock Nibi streamer — replays a stored historical orderbook day.

Drop-in replacement for `NibiStreamer`: same `(isins, redis_manager)`
constructor surface, same `nibi:{isin}:orderbook` Redis-stream key,
same `emit_bl` envelope (`event=BL`, `ts=<now>`, `data=<JSON>`), same
blocking `run()` / cooperative `stop()` lifecycle.

The mock replays one parquet file → one ISIN, so it accepts the same
list-shaped `isins` argument as the live streamer but requires exactly
one entry. Multi-ISIN multiplexing only makes sense for live hubs.

`ts` is current wall-clock (not the historical session time) so
downstream stale-quote detectors don't fire on replayed data.

`speed` controls replay pace assuming each parquet row is one second
of session time: `speed=1.0` → real-time; `speed=2.0` → 0.5s/row;
`speed=0.5` → 2s/row.
"""

from __future__ import annotations

import threading
from pathlib import Path

from historical import StorageClient
from redis_manager import RedisManager

from .adapter import to_bl
from ..base_streamer import BaseStreamer


class MockNibiStreamer(BaseStreamer):
    """Replay a stored orderbook day onto the same Redis stream a real
    `NibiStreamer` would publish to.

        from redis_manager import RedisManager
        from broker.nibi import MockNibiStreamer

        MockNibiStreamer(
            isins=["IRTKMOFD0001"],
            redis_manager=rm,
            parquet_path="data/orderbooks/IRTKMOFD0001_1403-12-01.parquet",
            speed=2.0,
        ).run()
    """

    def __init__(
        self,
        *,
        isins: list[str],
        redis_manager: RedisManager,
        parquet_path: Path | str,
        speed: float = 1.0,
        stream_maxlen: int | None = 10_000,
    ) -> None:
        super().__init__(isins=isins, redis_manager=redis_manager, stream_maxlen=stream_maxlen)
        if len(self.isins) != 1:
            raise ValueError(
                f"MockNibiStreamer: replay is single-instrument; got {len(self.isins)} isins"
            )
        if speed <= 0:
            raise ValueError("MockNibiStreamer: speed must be > 0")
        self.parquet_path = Path(parquet_path)
        if not self.parquet_path.is_file():
            raise FileNotFoundError(
                f"MockNibiStreamer: parquet file not found: {self.parquet_path}"
            )
        self.speed = speed
        self._stop = threading.Event()

    @classmethod
    def orderbook_stream_key(cls, isin: str) -> str:
        return f"nibi:{isin}:orderbook"

    @property
    def isin(self) -> str:
        return self.isins[0]

    def run(self) -> None:
        snapshots = StorageClient.load_orderbook_from_path(self.parquet_path)
        if not snapshots:
            self._log("mock", f"{self.parquet_path.name} has no rows, nothing to replay")
            return

        delay = 1.0 / self.speed
        self._log(
            "mock",
            f"replaying {len(snapshots)} rows from {self.parquet_path.name} "
            f"@ speed={self.speed}× → {self.orderbook_stream_key(self.isin)}",
        )

        self._stop.clear()
        for snap in snapshots:
            if self._stop.is_set():
                break
            payload = to_bl(snap, self.isin)
            try:
                self.emit_bl(self.isin, payload)
            except Exception as exc:
                self._log("emit_bl error", str(exc))
            if self._stop.wait(delay):
                break

        self._log("mock", "replay finished")

    def stop(self) -> None:
        self._stop.set()
