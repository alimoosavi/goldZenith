"""Live SignalR market-data clients (Pasargad).

    from redis_manager import RedisManager
    from broker_stream import PasargadStreamer, MockPasargadStreamer
    from settings import config

    rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
    rm.ping()
    PasargadStreamer(isin="IRTKMOFD0001", redis_manager=rm).run()

Each streamer publishes BL events to `{isin}:orderbook` on the shared
Redis. `PasargadStreamer` and `MockPasargadStreamer` have the same
public surface, so the mock can stand in anywhere the real one is used.
"""

from .pasargad import BaseStreamer, MockPasargadStreamer, PasargadStreamer

__all__ = ["BaseStreamer", "MockPasargadStreamer", "PasargadStreamer"]
