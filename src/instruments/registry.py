"""YAML-backed instrument registry: bridges TSETMC's `ins_code` and the
brokers' `isin`.

The same tradeable instrument carries two different identifiers in the
two halves of this codebase:

  - TSETMC's CDN URLs are keyed on a numeric `ins_code` (e.g.
    ``34144395039913458``) — see `historical.TSETMCClient`.
  - Pasargad and other brokers' SignalR feeds, plus the on-disk
    Parquet filenames and Redis stream keys, are keyed on the
    standardized 12-char `isin` (e.g. ``IRTKMOFD0001``) — see
    `broker.pasargad.PasargadStreamer` and `historical.StorageClient`.

The registry pins both ids together — plus a human-readable `symbol`
and `name` — in one place, so callers only have to know one identifier
and ask the registry to resolve the other.

The on-disk format is a top-level YAML list, one entry per instrument:

    - isin: IRTKMOFD0001
      ins_code: "34144395039913458"
      symbol: TKMOFD
      name: Mofid Treasury Fund
    - isin: IRTKROBA0001
      ins_code: ""
      symbol: ""
      name: ""

Empty strings are placeholders — entries can be added incrementally as
the mappings are discovered (e.g. by a backfill script that hits
TSETMC's search endpoint).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import yaml

from settings import config


@dataclass(frozen=True, slots=True)
class Instrument:
    """One tradeable instrument identified across both the TSETMC CDN
    (numeric `ins_code`) and broker SignalR feeds (12-char `isin`).

    `isin` is the canonical key — use it as the Redis-stream key prefix,
    Parquet filename component, etc. `ins_code` is only needed when
    talking to TSETMC's CDN and may be the empty string for entries
    whose mapping has not been backfilled yet.
    """

    isin: str
    ins_code: str = ""
    symbol: str = ""
    name: str = ""


class InstrumentRegistry:
    """In-memory view of the YAML registry with O(1) reverse lookups.

        from instruments import InstrumentRegistry

        reg = InstrumentRegistry()                    # loads config.instruments_file
        inst = reg.by_isin("IRTKMOFD0001")
        ins_code = inst.ins_code                      # for historical.TSETMCClient
        reg.add(Instrument(isin="...", ins_code="...", symbol="..."))
        reg.save()                                    # write back to disk

    Call `save()` after mutations to persist; loads happen automatically
    in `__init__`. `path=None` (the default) reads from
    `settings.config.instruments_file`.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config.instruments_file
        self._by_isin: dict[str, Instrument] = {}
        self._by_ins_code: dict[str, Instrument] = {}
        self._by_symbol: dict[str, Instrument] = {}
        if self.path.is_file():
            self._load()

    # ── persistence ─────────────────────────────────────────────────────

    def _load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        if not isinstance(raw, list):
            raise ValueError(
                f"{self.path}: expected top-level YAML list, got {type(raw).__name__}"
            )
        for entry in raw:
            inst = Instrument(
                isin=str(entry["isin"]).strip(),
                ins_code=str(entry.get("ins_code", "")).strip(),
                symbol=str(entry.get("symbol", "")).strip(),
                name=str(entry.get("name", "")).strip(),
            )
            self._index(inst)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [asdict(inst) for inst in self._by_isin.values()]
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(rows, f, sort_keys=False, allow_unicode=True)

    # ── indexing ────────────────────────────────────────────────────────

    def _index(self, inst: Instrument) -> None:
        if not inst.isin:
            raise ValueError("Instrument.isin must be a non-empty string")
        self._by_isin[inst.isin] = inst
        if inst.ins_code:
            self._by_ins_code[inst.ins_code] = inst
        if inst.symbol:
            self._by_symbol[inst.symbol] = inst

    # ── lookups ─────────────────────────────────────────────────────────

    def by_isin(self, isin: str) -> Instrument:
        try:
            return self._by_isin[isin]
        except KeyError:
            raise KeyError(f"unknown ISIN: {isin}") from None

    def by_ins_code(self, ins_code: str) -> Instrument:
        try:
            return self._by_ins_code[str(ins_code)]
        except KeyError:
            raise KeyError(f"unknown TSETMC ins_code: {ins_code}") from None

    def by_symbol(self, symbol: str) -> Instrument:
        try:
            return self._by_symbol[symbol]
        except KeyError:
            raise KeyError(f"unknown symbol: {symbol}") from None

    def get(self, key: str) -> Instrument | None:
        """Resolve by ISIN, ins_code, or symbol — whichever matches first."""
        return (
            self._by_isin.get(key)
            or self._by_ins_code.get(str(key))
            or self._by_symbol.get(key)
        )

    # ── mutation ────────────────────────────────────────────────────────

    def add(self, instrument: Instrument, *, overwrite: bool = False) -> None:
        if instrument.isin in self._by_isin and not overwrite:
            raise ValueError(f"ISIN already registered: {instrument.isin}")
        self._index(instrument)

    def upsert(self, instrument: Instrument) -> None:
        """Add or overwrite without raising."""
        self._index(instrument)

    # ── enumeration ─────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[Instrument]:
        return iter(self._by_isin.values())

    def __len__(self) -> int:
        return len(self._by_isin)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return (
            key in self._by_isin
            or key in self._by_ins_code
            or key in self._by_symbol
        )
