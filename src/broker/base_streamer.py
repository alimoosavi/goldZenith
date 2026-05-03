"""Abstract single-ISIN streamer that publishes BL events to Redis.

Concrete subclasses (`PasargadStreamer`, `MockPasargadStreamer`) plug in
the data source — a live SignalR hub for the real one, a random-payload
loop for the mock — but share the constructor shape, the Redis-stream
key (`{isin}:orderbook`), the BL payload envelope written via `emit_bl`,
and the blocking `run()` / cooperative `stop()` lifecycle. Callers can
swap implementations without touching the rest of their code.
"""

from __future__ import annotations

import abc
import json
import sys
from datetime import datetime, timezone
from typing import Any

from redis_manager import RedisManager


class BaseStreamer(abc.ABC):
    """Single-ISIN streamer base class.

    Implementations open whatever data source they need and call
    `emit_bl(payload)` to publish best-limits updates onto the
    `{isin}:orderbook` Redis stream. `run()` is blocking and must
    return cleanly when `stop()` is called.
    """

    EVENT_BL: str = "BL"

    def __init__(
        self,
        *,
        isin: str,
        redis_manager: RedisManager,
        stream_maxlen: int | None = 10_000,
    ) -> None:
        if not isin:
            raise ValueError(f"{type(self).__name__}: isin must be a non-empty string")
        self.isin = isin
        self.redis = redis_manager
        self.stream_maxlen = stream_maxlen

    @property
    def orderbook_stream_key(self) -> str:
        return f"{self.isin}:orderbook"

    def emit_bl(self, payload: Any) -> str:
        """Publish one BL event onto `{isin}:orderbook`.

        `payload` is the broker's BL data (typically a list of orderbook
        entries); it is serialized as JSON in a single `data` field
        alongside `event=BL` and a UTC ISO timestamp. Returns the Redis
        stream-entry id.
        """
        fields = {
            "event": self.EVENT_BL,
            "ts": datetime.now(timezone.utc).isoformat(),
            "data": json.dumps(payload, ensure_ascii=False),
        }
        return self.redis.xadd(
            self.orderbook_stream_key, fields, maxlen=self.stream_maxlen,
        )

    @abc.abstractmethod
    def run(self) -> None:
        """Blocking. Pump events until `stop()` is called."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Signal `run()` to exit cleanly."""

    def _log(self, tag: str, message: str) -> None:
        print(
            f"[{type(self).__name__} {self.isin}] {tag}: {message}",
            file=sys.stderr,
            flush=True,
        )
