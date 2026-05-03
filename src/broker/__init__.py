"""Per-broker market-data clients.

Each broker lives in its own subpackage (e.g. `broker.pasargad`) and
exposes the same shape: a `streamer.py` (real client subclassing
`broker.base_streamer.BaseStreamer`), a `mock_streamer.py`, and an
`adapter.py` with `to_bl` / `from_bl` to bridge the broker's wire
shape with the unified `OrderbookSnapshot` core. They all register
themselves in `broker.registry.BROKERS` so callers select brokers by
string name.

    from broker.registry import BROKERS, get_broker

    pas = get_broker("pasargad")
    pas.streamer_cls(isin=..., redis_manager=...)
"""

from .base_streamer import BaseStreamer
from .registry import BROKERS, BrokerEntry, get_broker

__all__ = ["BROKERS", "BaseStreamer", "BrokerEntry", "get_broker"]
