"""Abstract multi-ISIN streamer that publishes BL events to Redis.

Concrete subclasses (`NibiStreamer`, `PasargadStreamer`, ...) plug in
the data source — one shared SignalR hub connection per streamer
instance that subscribes to a batch of ISINs via the broker's REST
`SubscribeInstrument` endpoint — and share the constructor shape, the
per-ISIN Redis-stream key (`{broker}:{isin}:orderbook`, derived via the
abstract `orderbook_stream_key` classmethod each broker overrides), the
BL payload envelope written via `emit_bl`, and the blocking `run()` /
cooperative `stop()` lifecycle.
"""

from __future__ import annotations

import abc
import json
import sys
from datetime import datetime, timezone
from typing import Any

from redis_manager import RedisManager


class BaseStreamer(abc.ABC):
    """Multi-ISIN streamer base class.

    Implementations open a single broker connection that fans BL events
    out across `isins` and call `emit_bl(isin, payload)` per event to
    publish onto the per-ISIN `{broker}:{isin}:orderbook` Redis stream.
    `run()` is blocking and must return cleanly when `stop()` is called.
    """

    EVENT_BL: str = "BL"

    def __init__(
        self,
        *,
        isins: list[str],
        redis_manager: RedisManager,
        stream_maxlen: int | None = 10_000,
    ) -> None:
        if not isins:
            raise ValueError(f"{type(self).__name__}: isins must be a non-empty list")
        bad = [i for i in isins if not isinstance(i, str) or not i]
        if bad:
            raise ValueError(f"{type(self).__name__}: invalid isin entries: {bad}")
        self.isins: list[str] = list(isins)
        self.redis = redis_manager
        self.stream_maxlen = stream_maxlen

    @classmethod
    @abc.abstractmethod
    def orderbook_stream_key(cls, isin: str) -> str:
        """Return the Redis stream key for `isin` under this broker.

        Implementations must include the broker name as a prefix so
        streams from different brokers for the same ISIN never collide,
        e.g. `f"nibi:{isin}:orderbook"`. Declared as a classmethod so
        consumers (`feed.OrderbookFeed`, the persister, ...) can resolve
        keys via the streamer class without constructing an instance.
        """

    def emit_bl(self, isin: str, payload: Any) -> str:
        """Publish one BL event onto this broker's `{isin}:orderbook` stream.

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
            self.orderbook_stream_key(isin), fields, maxlen=self.stream_maxlen,
        )

    @abc.abstractmethod
    def run(self) -> None:
        """Blocking. Pump events until `stop()` is called."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Signal `run()` to exit cleanly."""

    @property
    def _log_prefix(self) -> str:
        if len(self.isins) == 1:
            return self.isins[0]
        return f"{self.isins[0]}+{len(self.isins) - 1}"

    def _log(self, tag: str, message: str) -> None:
        print(
            f"[{type(self).__name__} {self._log_prefix}] {tag}: {message}",
            file=sys.stderr,
            flush=True,
        )
