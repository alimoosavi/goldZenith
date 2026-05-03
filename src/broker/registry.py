"""Broker registry — looks up the streamer / mock-streamer / adapters
for a broker by name. Adding a new broker means dropping a sibling
package next to `pasargad/` (with `streamer.py` + `mock_streamer.py` +
`adapter.py` matching the same shape) and adding one entry to
`BROKERS` below; everything downstream — `feed.OrderbookFeed`, the
`scripts/feed.py` driver, the `scripts/broker_signalr_stream.py`
producer — discovers it through this table without per-broker
branching code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from historical import OrderbookSnapshot

from .base_streamer import BaseStreamer
from .pasargad import (
    MockPasargadStreamer,
    PasargadStreamer,
    from_bl as pasargad_from_bl,
    to_bl as pasargad_to_bl,
)


@dataclass(frozen=True, slots=True)
class BrokerEntry:
    """Per-broker class + adapter pointers.

    `streamer_cls` and `mock_streamer_cls` are subclasses of
    `BaseStreamer` that publish onto `{isin}:orderbook`; `to_bl`
    encodes a unified `OrderbookSnapshot` for the broker's wire format,
    `from_bl` decodes the wire payload back to `(isin, snapshot)` (the
    feed uses this on the consumer side).
    """

    name: str
    streamer_cls: type[BaseStreamer]
    mock_streamer_cls: type[BaseStreamer]
    to_bl: Callable[[OrderbookSnapshot, str], list[dict]]
    from_bl: Callable[[list[dict], str], tuple[str, OrderbookSnapshot]]


BROKERS: dict[str, BrokerEntry] = {
    "pasargad": BrokerEntry(
        name="pasargad",
        streamer_cls=PasargadStreamer,
        mock_streamer_cls=MockPasargadStreamer,
        to_bl=pasargad_to_bl,
        from_bl=pasargad_from_bl,
    ),
}


def get_broker(name: str) -> BrokerEntry:
    """Return the `BrokerEntry` for `name`, or raise with a helpful list."""
    try:
        return BROKERS[name]
    except KeyError:
        raise KeyError(
            f"unknown broker {name!r}; known: {sorted(BROKERS)}"
        ) from None
