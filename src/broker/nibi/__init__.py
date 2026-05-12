"""Nibi broker — live + mock streamers, BL adapter.

Wire-compatible with `broker.pasargad`: same SignalR handshake, same
REST `SubscribeInstrument` shape, same BL outer envelope and depth
field names. Only the URLs and credentials differ. Kept as a separate
package (rather than re-exporting Pasargad's adapter) so the two
brokers can diverge later without churn.

Registered in `broker.registry.BROKERS["nibi"]` with the full quartet
(streamer, mock_streamer, to_bl, from_bl), so `broker.make_streamer`,
`feed.OrderbookFeed`, and the replay scripts work without any
broker-specific branching.
"""

from .adapter import from_bl, to_bl
from .mock_streamer import MockNibiStreamer
from .streamer import NibiStreamer

__all__ = ["MockNibiStreamer", "NibiStreamer", "from_bl", "to_bl"]
