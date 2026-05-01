"""Print the contents of a Parquet file to stdout.

Usage:

    uv run python scripts/show_parquet.py <path.parquet> [--rows N] [--all]

Bare filenames resolve under `ORDERBOOKS_DIR` first, then `TRADES_DIR`,
so you can pass e.g. `34144395039913458_1405-01-11.parquet` directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow.parquet as pq

from settings import config


def resolve_path(arg: str) -> Path:
    p = Path(arg).expanduser()
    if p.is_file():
        return p.resolve()
    for root in (config.orderbooks_dir, config.trades_dir):
        candidate = root / p.name
        if candidate.is_file():
            return candidate.resolve()
    sys.exit(f"ERROR: file not found — tried {p}, {config.orderbooks_dir / p.name}, {config.trades_dir / p.name}")


def print_rows(table, limit: int | None) -> None:
    n = table.num_rows if limit is None else min(limit, table.num_rows)
    cols = table.column_names
    widths = [max(len(c), 12) for c in cols]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for i in range(n):
        row = [table.column(c)[i].as_py() for c in cols]
        cells = [
            f"{v:,.4f}" if isinstance(v, float)
            else f"{v:,}" if isinstance(v, int)
            else "" if v is None
            else str(v)
            for v in row
        ]
        print("  ".join(cell.ljust(w) for cell, w in zip(cells, widths)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="Parquet file path or bare filename under orderbooks/trades dir")
    ap.add_argument("--rows", type=int, default=20, help="Rows to preview (default: 20)")
    ap.add_argument("--all", action="store_true", help="Print every row (overrides --rows)")
    args = ap.parse_args()

    path = resolve_path(args.path)
    table = pq.read_table(path)
    size = path.stat().st_size

    print(f"file:    {path}")
    print(f"size:    {size:,} bytes")
    print(f"rows:    {table.num_rows:,}")
    print(f"columns: {table.num_columns}")
    print("\nschema:")
    for f in table.schema:
        print(f"  {f.name:<20} {f.type}")

    if table.num_rows == 0:
        print("\n(empty table)")
        return

    limit = None if args.all else args.rows
    label = "all rows" if args.all else f"first {min(args.rows, table.num_rows)} of {table.num_rows} row(s)"
    print(f"\n{label}:")
    print_rows(table, limit)


if __name__ == "__main__":
    main()
