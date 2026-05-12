"""Verify per-day orderbook + trade Parquet files exist for every (ISIN, Jalali date).

For each instrument (from `--isin-file` if given, else every entry in
the registry) and each Jalali date in `[--start, --end]` inclusive,
checks both `{ORDERBOOKS_DIR}/{isin}_{date}.parquet` and
`{TRADES_DIR}/{isin}_{date}.parquet`. Prints a per-instrument summary
of coverage; with `--verbose`, lists every missing (isin, date, kind).

Useful as a post-`fetch_range` sanity check — exits 0 if everything
is complete, 1 if any file is missing, so it slots into CI / a
Taskfile gate.

Note: missing files may legitimately correspond to non-trading days
(Persian-week weekends, public holidays). This script does not try to
filter those — it just reports the raw on-disk picture.

Examples:
    uv run python scripts/verify_range.py --start 1403-01-01 --end 1404-12-08
    uv run python scripts/verify_range.py --start 1403-01-01 --end 1404-12-08 \\
        --isin-file data/instruments_isin_list.json --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta

import jdatetime

from historical import StorageClient
from instruments import InstrumentRegistry


def jalali_daterange(start: str, end: str) -> list[str]:
    """Inclusive list of Jalali date strings (YYYY-MM-DD) from start → end."""
    sy, sm, sd = (int(x) for x in start.split("-"))
    ey, em, ed = (int(x) for x in end.split("-"))
    cur = jdatetime.date(sy, sm, sd)
    last = jdatetime.date(ey, em, ed)
    if cur > last:
        sys.exit(f"--start {start} is after --end {end}")
    out: list[str] = []
    while cur <= last:
        out.append(f"{cur.year:04d}-{cur.month:02d}-{cur.day:02d}")
        cur += timedelta(days=1)
    return out


def _load_isins(args, registry: InstrumentRegistry) -> list[str]:
    if args.isin_file:
        try:
            with open(args.isin_file) as f:
                isins = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            sys.exit(f"Failed to load {args.isin_file}: {e}")
        if not isinstance(isins, list) or not isins:
            sys.exit(f"{args.isin_file} must contain a non-empty JSON list of ISINs")
    else:
        isins = [inst.isin for inst in registry]
    if not isins:
        sys.exit("no ISINs to verify (registry is empty and --isin-file not given)")
    for isin in isins:
        if isin not in registry:
            sys.exit(f"ISIN {isin} is not in the registry ({registry.path})")
    return isins


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", required=True, help="Jalali start date YYYY-MM-DD (inclusive)")
    ap.add_argument("--end",   required=True, help="Jalali end date YYYY-MM-DD (inclusive)")
    ap.add_argument(
        "--isin-file", metavar="PATH",
        help="JSON file with a list of ISINs to verify. "
             "Defaults to every instrument in the registry.",
    )
    ap.add_argument(
        "--verbose", action="store_true",
        help="Print one line per missing (isin, date, kind) gap",
    )
    args = ap.parse_args()

    registry = InstrumentRegistry()
    isins = _load_isins(args, registry)
    dates = jalali_daterange(args.start, args.end)
    total = len(dates)
    store = StorageClient()

    print(
        f"Verifying {len(isins)} ISIN(s) × {total} day(s) "
        f"{dates[0]} → {dates[-1]}"
    )
    print(f"  orderbooks ← {store.orderbooks_dir}")
    print(f"  trades     ← {store.trades_dir}\n")

    grand_missing_ob = 0
    grand_missing_tr = 0
    instruments_with_gaps = 0

    for isin in isins:
        inst = registry.by_isin(isin)
        label = inst.symbol or isin
        missing_ob = [d for d in dates if not store.has_orderbook(isin, d)]
        missing_tr = [d for d in dates if not store.has_trades(isin, d)]
        gaps = bool(missing_ob or missing_tr)
        instruments_with_gaps += int(gaps)

        status = "GAPS" if gaps else " OK "
        print(
            f"• [{status}] {label:<14} {isin}  "
            f"orderbooks {total - len(missing_ob):>4}/{total}  "
            f"trades {total - len(missing_tr):>4}/{total}"
        )

        if args.verbose:
            for d in missing_ob:
                print(f"    missing orderbook  {isin}  {d}")
            for d in missing_tr:
                print(f"    missing trades     {isin}  {d}")

        grand_missing_ob += len(missing_ob)
        grand_missing_tr += len(missing_tr)

    print()
    print(
        f"Summary: {len(isins) - instruments_with_gaps}/{len(isins)} instrument(s) complete  "
        f"│  missing orderbooks: {grand_missing_ob}  │  missing trades: {grand_missing_tr}"
    )
    sys.exit(1 if grand_missing_ob or grand_missing_tr else 0)


if __name__ == "__main__":
    main()
