"""Unified streamer factory — pick a broker by name, get back a ready
`BaseStreamer` for a batch of ISINs.

    from broker import make_streamer
    from redis_manager import RedisManager
    from settings import config

    rm = RedisManager(uri=config.redis_uri, port=config.redis_port); rm.ping()
    s = make_streamer(
        broker="nibi",
        isins=["IRTKMOFD0001", "IRTKROBA0001"],
        redis_manager=rm,
    )
    s.run()      # blocking; XADDs to nibi:{isin}:orderbook per ISIN

`mock=True` swaps in the broker's mock-streamer, which replays a single
parquet so `isins` must have exactly one entry (the mock validates this
in its constructor). Brokers that don't ship a mock raise a clear
`LookupError` instead of `AttributeError`.

This is the only place callers should construct streamers — keep
broker-specific class names out of script and feed code.
"""

from __future__ import annotations

from redis_manager import RedisManager

from .base_streamer import BaseStreamer
from .registry import get_broker


def make_streamer(
    *,
    broker: str,
    isins: list[str],
    redis_manager: RedisManager,
    mock: bool = False,
    **kwargs,
) -> BaseStreamer:
    """Return a configured streamer for `(broker, isins)`.

    Extra `kwargs` are forwarded to the streamer's constructor — use
    them for live-only knobs (e.g. `auth_token=`, `heartbeat_interval=`)
    or mock-only knobs (e.g. `parquet_path=`, `speed=`). The Redis
    stream key is owned by the broker's `orderbook_stream_key`
    classmethod (`{broker}:{isin}:orderbook`).
    """
    entry = get_broker(broker)
    if mock:
        cls = entry.mock_streamer_cls
        if cls is None:
            raise LookupError(
                f"broker {broker!r} has no mock streamer registered "
                f"(add a `mock_streamer_cls` to `BROKERS[{broker!r}]` first)"
            )
    else:
        cls = entry.streamer_cls
    return cls(isins=isins, redis_manager=redis_manager, **kwargs)
