"""Broker registry — looks up the streamer / mock-streamer / adapters
for a broker by name. Adding a new broker means dropping a sibling
package next to `pasargad/` and adding one entry to `BROKERS` below;
everything downstream — `broker.make_streamer`, `feed.OrderbookFeed`,
the `scripts/broker_signalr_stream.py` producer — discovers it through
this table without per-broker branching code.

A broker is only required to expose `streamer_cls`. `mock_streamer_cls`,
`to_bl`, and `from_bl` are optional — brokers that haven't shipped a
mock or BL adapter yet leave them `None`, and consumers that need them
(replay, `OrderbookFeed`) raise a helpful error when invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from historical import OrderbookSnapshot

from .base_streamer import BaseStreamer
from .nibi import (
    MockNibiStreamer,
    NibiStreamer,
    from_bl as nibi_from_bl,
    to_bl as nibi_to_bl,
)
from .pasargad import (
    MockPasargadStreamer,
    PasargadStreamer,
    from_bl as pasargad_from_bl,
    to_bl as pasargad_to_bl,
)


@dataclass(frozen=True, slots=True)
class BrokerEntry:
    """Per-broker class + adapter pointers.

    `streamer_cls` is the live streamer (required, subclass of
    `BaseStreamer` publishing onto `{isin}:orderbook`).
    `mock_streamer_cls` is the parquet-replay equivalent.
    `to_bl` encodes a unified `OrderbookSnapshot` for the broker's wire
    format; `from_bl` decodes the wire payload back to
    `(isin, snapshot)`. The optional fields stay `None` for brokers
    that haven't shipped them yet.
    """

    name: str
    streamer_cls: type[BaseStreamer]
    mock_streamer_cls: Optional[type[BaseStreamer]] = None
    to_bl: Optional[Callable[[OrderbookSnapshot, str], list[dict]]] = None
    from_bl: Optional[Callable[[list[dict], str], tuple[str, OrderbookSnapshot]]] = None


BROKERS: dict[str, BrokerEntry] = {
    "pasargad": BrokerEntry(
        name="pasargad",
        streamer_cls=PasargadStreamer,
        mock_streamer_cls=MockPasargadStreamer,
        to_bl=pasargad_to_bl,
        from_bl=pasargad_from_bl,
    ),
    "nibi": BrokerEntry(
        name="nibi",
        streamer_cls=NibiStreamer,
        mock_streamer_cls=MockNibiStreamer,
        to_bl=nibi_to_bl,
        from_bl=nibi_from_bl,
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