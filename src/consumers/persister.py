"""Append every orderbook update to durable per-ISIN JSONL files.

One file per `(isin, UTC date)` under `out_dir`:

    out_dir/{isin}/{YYYY-MM-DD}.jsonl

Each line is a self-contained record carrying the envelope `ts`, the
Redis `stream_id`, and the decoded `OrderbookSnapshot` flattened to a
plain dict — directly loadable with `pandas.read_json(..., lines=True)`
for offline analysis.

Durability notes:

  - Uses plain `XREAD` via `OrderbookFeed`, which tracks `last_ids` in
    memory only. On a crash, anything `XADD`ed between the most recent
    `fh.flush()` and the crash is lost. For at-least-once durability,
    swap to `XREADGROUP` with a consumer group and `XACK` only after
    `flush()` returns — left as a follow-up, since file-system append
    + per-batch flush is durable enough for the v1 use case.
  - `{isin}:orderbook` is capped by the streamer (`stream_maxlen=10_000`
    by default). A persister stall longer than ~10–30 min during active
    trading will silently drop entries off the tail. Bump the
    streamer's cap once this is the system of record.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TextIO

from feed import BookUpdate, OrderbookFeed
from redis_manager import RedisManager


class OrderbookPersister:
    """Tail one or more `{isin}:orderbook` streams and append decoded
    snapshots to JSONL files, one per `(isin, UTC date)`. Daily
    rollover happens lazily on the next write — gaps over midnight are
    expected and not a bug."""

    def __init__(
        self,
        broker: str,
        isins: list[str],
        out_dir: Path | str,
        *,
        redis_manager: RedisManager | None = None,
        flush_every: int = 1,
    ) -> None:
        if flush_every < 1:
            raise ValueError("OrderbookPersister: flush_every must be >= 1")
        self.out_dir = Path(out_dir)
        self.flush_every = flush_every
        self._files: dict[tuple[str, date], TextIO] = {}
        self._writes_since_flush = 0
        self._counts: dict[str, int] = {}
        self.feed = OrderbookFeed(
            broker=broker,
            isins=isins,
            on_update=self._on_update,
            redis_manager=redis_manager,
        )

    def run(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.feed.run()
        finally:
            self._close_all()

    def stop(self) -> None:
        self.feed.stop()

    @property
    def written(self) -> int:
        return sum(self._counts.values())

    @property
    def counts_by_isin(self) -> dict[str, int]:
        return dict(self._counts)

    def _on_update(self, update: BookUpdate) -> None:
        fh = self._file_for(update.isin, _date_of(update.ts))
        record = {
            "isin": update.isin,
            "ts": update.ts,
            "stream_id": update.stream_id,
            "snapshot": {
                "time": update.snapshot.time,
                "depths": [asdict(d) for d in update.snapshot.depths],
            },
        }
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")
        self._counts[update.isin] = self._counts.get(update.isin, 0) + 1
        self._writes_since_flush += 1
        if self._writes_since_flush >= self.flush_every:
            fh.flush()
            self._writes_since_flush = 0

    def _file_for(self, isin: str, day: date) -> TextIO:
        key = (isin, day)
        fh = self._files.get(key)
        if fh is None:
            isin_dir = self.out_dir / isin
            isin_dir.mkdir(parents=True, exist_ok=True)
            fh = (isin_dir / f"{day.isoformat()}.jsonl").open("a", encoding="utf-8")
            self._files[key] = fh
        return fh

    def _close_all(self) -> None:
        for fh in self._files.values():
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass
        self._files.clear()


def _date_of(ts_iso: str) -> date:
    if not ts_iso:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.fromisoformat(ts_iso).date()
    except ValueError:
        return datetime.now(timezone.utc).date()