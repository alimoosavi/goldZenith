"""Per-broker market-data clients.

Each broker lives in its own subpackage (e.g. `broker.pasargad`,
`broker.nibi`) and exposes the same shape: a `streamer.py` (real
client subclassing `broker.base_streamer.BaseStreamer`), optionally a
`mock_streamer.py`, and optionally an `adapter.py` with `to_bl` /
`from_bl` to bridge the broker's wire shape with the unified
`OrderbookSnapshot` core. They all register themselves in
`broker.registry.BROKERS` so callers select brokers by string name.

Construct a streamer through the unified factory rather than
referencing per-broker classes directly:

    from broker import make_streamer
    s = make_streamer(broker="nibi", isin=..., redis_manager=...)
    s.run()                                  # live → {isin}:orderbook
"""

from .base_streamer import BaseStreamer
from .factory import make_streamer
from .registry import BROKERS, BrokerEntry, get_broker

__all__ = [
    "BROKERS",
    "BaseStreamer",
    "BrokerEntry",
    "get_broker",
    "make_streamer",
]
