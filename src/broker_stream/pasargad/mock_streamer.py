"""Mock Pasargad streamer — random BL events on the same Redis stream.

Drop-in replacement for `PasargadStreamer`: same `(isin, redis_manager)`
constructor, same `{isin}:orderbook` stream key, same `emit_bl` envelope
shape, same blocking `run()` / cooperative `stop()` lifecycle. The only
difference is the data source — instead of opening a SignalR socket,
this loops on a timer and emits random 5-depth payloads. Useful for
offline development, integration tests, and consumer-side iteration
without needing a live broker session.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable

from redis_manager import RedisManager

from .base import BaseStreamer

MessageHandler = Callable[[str, list], None]


class MockPasargadStreamer(BaseStreamer):
    """Random-BL streamer with the same public surface as the real client.

        from redis_manager import RedisManager
        from broker_stream import MockPasargadStreamer
        from settings import config

        rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
        MockPasargadStreamer(
            isin="IRTKMOFD0001",
            redis_manager=rm,
            tick_interval=0.5,
        ).run()

    Each tick emits one BL payload shaped like the real broker's
    (`{id, instrumentId, data: [{index, zOrdMeDem, qTitMeDem, pMeDem, …}, …×5]}`)
    so a downstream consumer reading the Redis stream can't tell mock
    from real by payload shape alone.
    """

    def __init__(
        self,
        *,
        isin: str,
        redis_manager: RedisManager,
        tick_interval: float = 0.5,
        base_price: float = 50_000.0,
        seed: int | None = None,
        stream_maxlen: int | None = 10_000,
        on_message: MessageHandler | None = None,
    ) -> None:
        super().__init__(isin=isin, redis_manager=redis_manager, stream_maxlen=stream_maxlen)
        if tick_interval <= 0:
            raise ValueError("MockPasargadStreamer: tick_interval must be > 0")
        if base_price <= 0:
            raise ValueError("MockPasargadStreamer: base_price must be > 0")

        self.tick_interval = tick_interval
        self.base_price = base_price
        self._rng = random.Random(seed)
        self._on_message_user = on_message
        self._stop = threading.Event()

    def run(self) -> None:
        """Blocking. Emits one random BL payload every `tick_interval`
        seconds until `stop()` is called."""
        self._stop.clear()
        self._log(
            "mock",
            f"emitting random BL every {self.tick_interval}s on {self.orderbook_stream_key}",
        )
        while not self._stop.wait(self.tick_interval):
            payload = self._random_bl_payload()
            try:
                self.emit_bl(payload)
            except Exception as exc:
                self._log("emit_bl error", str(exc))
                continue
            if self._on_message_user is not None:
                try:
                    self._on_message_user(self.EVENT_BL, payload)
                except Exception as exc:
                    self._log("on_message error", str(exc))

    def stop(self) -> None:
        self._stop.set()

    # ── payload synthesis ───────────────────────────────────────────────

    def _random_bl_payload(self) -> list[dict]:
        base = self.base_price * self._rng.uniform(0.99, 1.01)
        tick = max(1.0, base * 0.0005)
        depths = [
            {
                "index":     d,
                "zOrdMeDem": self._rng.randint(1, 50),
                "qTitMeDem": self._rng.randint(100, 100_000),
                "pMeDem":    round(base - tick * d, 2),
                "zOrdMeOf":  self._rng.randint(1, 50),
                "qTitMeOf":  self._rng.randint(100, 100_000),
                "pMeOf":     round(base + tick * d, 2),
            }
            for d in range(1, 6)
        ]
        return [
            {
                "id":           int(time.time() * 1_000),
                "instrumentId": self.isin,
                "data":         depths,
            }
        ]
