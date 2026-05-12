"""Mock Pasargad streamer — replays a stored historical orderbook day.

Drop-in replacement for `PasargadStreamer`: same `(isins, redis_manager)`
constructor surface, same `pasargad:{isin}:orderbook` Redis-stream key,
same `emit_bl` envelope (`event=BL`, `ts=<now>`, `data=<JSON>`), same
blocking `run()` / cooperative `stop()` lifecycle.

The mock replays one parquet file → one ISIN, so it accepts the same
list-shaped `isins` argument as the live streamer but requires exactly
one entry. Multi-ISIN multiplexing only makes sense for live hubs.

The parquet path is derived from `config.orderbooks_dir` and the project
naming convention `{isin}_{jalali_date}.parquet` — callers pass a Jalali
date and the mock resolves the path itself.

`ts` is current wall-clock (not the historical session time) so
downstream stale-quote detectors don't fire on replayed data.

`speed` controls replay pace assuming each parquet row is one second
of session time.
"""

from __future__ import annotations

import threading

from historical import StorageClient
from redis_manager import RedisManager
from settings import config

from .adapter import to_bl
from ..base_streamer import BaseStreamer


class MockPasargadStreamer(BaseStreamer):
    """Replay a stored orderbook day onto the same Redis stream a real
    `PasargadStreamer` would publish to."""

    def __init__(
        self,
        *,
        isins: list[str],
        redis_manager: RedisManager,
        jalali_date: str,
        speed: float = 1.0,
        stream_maxlen: int | None = 10_000,
    ) -> None:
        super().__init__(isins=isins, redis_manager=redis_manager, stream_maxlen=stream_maxlen)
        if len(self.isins) != 1:
            raise ValueError(
                f"MockPasargadStreamer: replay is single-instrument; got {len(self.isins)} isins"
            )
        if not jalali_date:
            raise ValueError("MockPasargadStreamer: jalali_date must be non-empty")
        if speed <= 0:
            raise ValueError("MockPasargadStreamer: speed must be > 0")
        self.jalali_date = jalali_date
        self.parquet_path = config.orderbooks_dir / f"{self.isins[0]}_{jalali_date}.parquet"
        if not self.parquet_path.is_file():
            raise FileNotFoundError(
                f"MockPasargadStreamer: parquet file not found: {self.parquet_path}"
            )
        self.speed = speed
        self._stop = threading.Event()

    @classmethod
    def orderbook_stream_key(cls, isin: str) -> str:
        return f"pasargad:{isin}:orderbook"

    @property
    def isin(self) -> str:
        return self.isins[0]

    def run(self) -> None:
        snapshots = StorageClient.load_orderbook_from_path(self.parquet_path)
        if not snapshots:
            self._log("mock", f"{self.parquet_path.name} has no rows, nothing to replay")
            return

        # Drop CDN head/tail noise outside the trading-session window.
        raw_count = len(snapshots)
        open_t, end_t = config.market_open, config.market_end
        snapshots = [s for s in snapshots if open_t <= s.time <= end_t]
        if not snapshots:
            self._log(
                "mock",
                f"{self.parquet_path.name}: all {raw_count} rows outside "
                f"[{open_t}, {end_t}], nothing to replay",
            )
            return

        delay = 1.0 / self.speed
        self._log(
            "mock",
            f"replaying {len(snapshots)}/{raw_count} rows from {self.parquet_path.name} "
            f"(window [{open_t}, {end_t}]) @ speed={self.speed}× → "
            f"{self.orderbook_stream_key(self.isin)}",
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
