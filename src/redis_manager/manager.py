"""Thin wrapper over redis-py with stream-key conventions for this project."""

from __future__ import annotations

from typing import Any

import redis


class RedisManager:
    """Single-instance Redis client with stream-friendly helpers.

        from settings import config
        from redis_manager import RedisManager

        rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
        rm.xadd("ABC123:orderbook", {"event": "BL", "data": "..."})

    The underlying `redis.Redis` connection pool is created lazily, so
    constructing a `RedisManager` does not require a live server. Call
    `ping()` to verify connectivity.
    """

    def __init__(
        self,
        *,
        uri: str,
        port: int,
        db: int = 0,
        decode_responses: bool = True,
    ) -> None:
        self.uri = uri
        self.port = port
        self.db = db
        self.client = redis.Redis(
            host=uri,
            port=port,
            db=db,
            decode_responses=decode_responses,
        )

    # ── connectivity ────────────────────────────────────────────────────

    def ping(self) -> bool:
        return bool(self.client.ping())

    # ── streams ─────────────────────────────────────────────────────────

    def xadd(
        self,
        stream: str,
        fields: dict[str, Any],
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        """Publish one entry. `maxlen` (with `approximate=True`) caps the
        stream length so producers don't grow it unbounded."""
        kwargs: dict[str, Any] = {}
        if maxlen is not None:
            kwargs["maxlen"] = maxlen
            kwargs["approximate"] = approximate
        return self.client.xadd(stream, fields, **kwargs)

    def xrange(
        self,
        stream: str,
        *,
        min: str = "-",
        max: str = "+",
        count: int | None = None,
    ) -> list:
        return self.client.xrange(stream, min=min, max=max, count=count)

    def xlen(self, stream: str) -> int:
        return self.client.xlen(stream)

    def xread(
        self,
        streams: dict[str, str],
        *,
        count: int | None = None,
        block: int | None = None,
    ) -> list:
        """Blocking read across one or more streams. `streams` maps key →
        last-id (`"$"` = only new entries; `"0"` = from the beginning)."""
        return self.client.xread(streams, count=count, block=block)
