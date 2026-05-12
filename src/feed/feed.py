"""Multi-broker, multi-ISIN orderbook feed.

`OrderbookFeed` is a pure consumer — it doesn't know whether the events
it reads originated from a live SignalR client or a parquet-replay
mock. It opens a single multi-stream `XREAD` against every
`{broker}:{isin}:orderbook` key in `isins` (key format owned by the
broker's `orderbook_stream_key` classmethod), decodes each entry's
`data` JSON through the selected broker's `from_bl` adapter, wraps the
result in a typed `BookUpdate(isin, ts, snapshot, stream_id)`, and
dispatches to the user-provided `on_update` callback in arrival order.

Selecting the broker is a string lookup against `broker.registry.BROKERS`
so the feed is broker-agnostic at the call site:

    feed = OrderbookFeed(
        broker="pasargad",
        isins=["IRTKLOTF0001", "IRTKMOFD0001"],
        on_update=lambda u: print(u.isin, u.snapshot.depths[0].buy_price),
    )
    feed.run()                  # blocking
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Callable

from broker.registry import BROKERS, BrokerEntry
from historical import OrderbookSnapshot
from redis_manager import RedisManager
from settings import config


@dataclass(frozen=True, slots=True)
class BookUpdate:
    """One decoded orderbook update flowing out of the feed.

    `ts` is the envelope timestamp (ISO 8601 UTC) the producer attached
    when it XADDed the entry — current wall-clock for both real and
    mock streamers, which matters for downstream consumers that filter
    on event freshness."""

    isin: str
    ts: str
    snapshot: OrderbookSnapshot
    stream_id: str


class OrderbookFeed:
    """Subscribe to `{broker}:{isin}:orderbook` streams across N instruments
    and dispatch typed `BookUpdate`s to a callback.

    `block_ms=0` would block forever inside redis-py; using a finite
    timeout (default 1000ms) lets `stop()` take effect in <1s without
    eating CPU between events. `last_ids` lets you resume from a known
    id (e.g. after a crash) — default `"$"` per stream means
    only-new-events.
    """

    def __init__(
        self,
        broker: str,
        isins: list[str],
        on_update: Callable[[BookUpdate], None],
        *,
        redis_manager: RedisManager | None = None,
        last_ids: dict[str, str] | None = None,
        block_ms: int = 1000,
        count: int = 100,
    ) -> None:
        if not isins:
            raise ValueError("OrderbookFeed: isins list is empty")
        if broker not in BROKERS:
            raise ValueError(
                f"OrderbookFeed: unknown broker {broker!r}; known: {sorted(BROKERS)}"
            )
        if BROKERS[broker].from_bl is None:
            raise ValueError(
                f"OrderbookFeed: broker {broker!r} has no `from_bl` adapter "
                f"registered — it can produce streams but the feed can't decode them"
            )

        self.broker_entry: BrokerEntry = BROKERS[broker]
        self.isins: list[str] = list(isins)
        self.on_update = on_update
        self.redis = redis_manager or RedisManager(
            uri=config.redis_uri, port=config.redis_port,
        )
        key_for = self.broker_entry.streamer_cls.orderbook_stream_key
        self.last_ids: dict[str, str] = (
            dict(last_ids)
            if last_ids
            else {key_for(i): "$" for i in self.isins}
        )
        self.block_ms = block_ms
        self.count = count
        self._stop = threading.Event()

    def run(self) -> None:
        """Blocking loop. Returns when `stop()` is called."""
        from_bl = self.broker_entry.from_bl
        self._stop.clear()
        while not self._stop.is_set():
            resp = self.redis.xread(
                self.last_ids, block=self.block_ms, count=self.count,
            ) or []
            for stream_key, entries in resp:
                for stream_id, fields in entries:
                    self.last_ids[stream_key] = stream_id
                    try:
                        payload = json.loads(fields["data"])
                        isin, snapshot = from_bl(payload, fields.get("ts", ""))
                    except Exception as exc:
                        print(
                            f"[OrderbookFeed] decode error on {stream_key}/{stream_id}: {exc}"
                        )
                        continue
                    update = BookUpdate(
                        isin=isin, ts=fields.get("ts", ""),
                        snapshot=snapshot, stream_id=stream_id,
                    )
                    try:
                        self.on_update(update)
                    except Exception as exc:
                        print(
                            f"[OrderbookFeed] on_update error: {exc}"
                        )

    def stop(self) -> None:
        self._stop.set()
