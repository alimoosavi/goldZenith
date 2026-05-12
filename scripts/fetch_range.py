"""Fetch and persist historical orderbook + trade data over a Jalali date range.

Walks every Jalali day in `[--start, --end]` (inclusive), pulls the
per-second 5-depth orderbook snapshots and tick-by-tick trades for
one or more ISINs, and writes them through `historical.StorageClient` as
`{isin}_{jalali}.parquet` under `ORDERBOOKS_DIR` / `TRADES_DIR`. Days
already on disk are skipped unless `--force` is passed.

ISIN is the canonical identifier across the project; this script
resolves it to TSETMC's numeric `ins_code` via `InstrumentRegistry`
just before each CDN call. The registry entry must therefore have
`ins_code` populated.

Examples:

    # Single ISIN
    uv run python scripts/fetch_range.py \\
        --isin IRTKMOFD0001 \\
        --start 1405-01-01 --end 1405-02-01

    # Multiple ISINs from JSON file
    uv run python scripts/fetch_range.py \\
        --isin-file isins.json \\
        --start 1405-01-01 --end 1405-02-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta

import jdatetime

from historical import StorageClient, TSETMCClient
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


def resolve_isin(registry: InstrumentRegistry, isin: str) -> tuple[str, str]:
    """Resolve ISIN to (isin, ins_code), validating registry entry exists and has ins_code.

    Returns (isin, ins_code) on success; exits with error message on failure.
    """
    try:
        instrument = registry.by_isin(isin)
    except KeyError:
        sys.exit(f"ISIN {isin} is not in the registry ({registry.path})")
    if not instrument.ins_code:
        sys.exit(f"registry entry for {isin} has no ins_code — backfill it before fetching")
    return isin, instrument.ins_code


def fetch_one(
    client: TSETMCClient, store: StorageClient,
    isin: str, ins_code: str, date: str, force: bool,
) -> None:
    ob_cached = store.has_orderbook(isin, date) and not force
    tr_cached = store.has_trades(isin, date) and not force
    if ob_cached and tr_cached:
        print(f"{date}: cached, skip")
        return

    try:
        if not ob_cached:
            snaps = client.fetch_orderbook_snapshots(ins_code, date)
            path = store.save_orderbook(isin, date, snaps)
            print(f"{date}: orderbook  {len(snaps):>6} rows → {path.name}")
        if not tr_cached:
            trades = client.fetch_trades(ins_code, date)
            path = store.save_trades(isin, date, trades)
            print(f"{date}: trades     {len(trades):>6} rows → {path.name}")
    except Exception as e:
        print(f"{date}: ERROR — {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    isin_group = ap.add_mutually_exclusive_group(required=True)
    isin_group.add_argument("--isin", help="Single 12-char ISIN (must be in the registry)")
    isin_group.add_argument("--isin-file", metavar="PATH",
                           help="JSON file containing list of ISINs")
    ap.add_argument("--start", required=True, help="Jalali start date YYYY-MM-DD (inclusive)")
    ap.add_argument("--end",   required=True, help="Jalali end date YYYY-MM-DD (inclusive)")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch and overwrite even if a cached file exists")
    args = ap.parse_args()

    # Load ISINs from either --isin or --isin-file
    if args.isin:
        isins = [args.isin]
    else:
        try:
            with open(args.isin_file) as f:
                isins = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            sys.exit(f"Failed to load {args.isin_file}: {e}")
        if not isinstance(isins, list) or not isins:
            sys.exit(f"{args.isin_file} must contain a non-empty JSON list of ISINs")

    # Resolve all ISINs upfront (fail-fast)
    registry = InstrumentRegistry()
    isin_pairs = []
    for isin in isins:
        isin_pairs.append(resolve_isin(registry, isin))

    client = TSETMCClient()
    store = StorageClient()
    dates = jalali_daterange(args.start, args.end)

    print(f"Fetching {len(isins)} ISIN(s): {len(dates)} day(s) {dates[0]} → {dates[-1]}")
    print(f"  orderbooks → {store.orderbooks_dir}")
    print(f"  trades     → {store.trades_dir}\n")

    for isin, ins_code in isin_pairs:
        instrument = registry.by_isin(isin)
        label = f"{instrument.symbol or instrument.isin} ({ins_code})"
        print(f"• {label}")
        for date in dates:
            fetch_one(client, store, isin, ins_code, date, args.force)
        print()


if __name__ == "__main__":
    main()
