"""Fetch order history for a given date via the Nibi broker REST API.

Edit HISTORY_DATE below (or leave as None for today), then:

    uv run python scripts/get_orders.py

Auth + endpoint come from `config` (NIBI_AUTH_TOKEN, NIBI_COOKIE,
NIBI_RED_ENDPOINT_BASE_URL in `.env`).
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict

import aiohttp

from broker.nibi import NibiBrokerClient
from settings import config

# ── History date ─────────────────────────────────────────────────────────────
HISTORY_DATE: str | None = "20260513"        # None → today; or e.g. "20250226"


async def main() -> None:
    async with NibiBrokerClient(
        auth_token=config.nibi_auth_token,
        cookie=config.nibi_cookie,
        red_endpoint_base_url=config.nibi_red_endpoint_base_url,
    ) as client:
        try:
            resp = await client.get_orders(history_date=HISTORY_DATE)
        except aiohttp.ClientResponseError as e:
            print(f"❌ HTTP Error: {e.status} - {e.message}")
            sys.exit(1)
        except aiohttp.ClientConnectionError:
            print("❌ Connection Error: Could not reach the endpoint.")
            sys.exit(1)
        except aiohttp.ClientError as e:
            print(f"❌ Request failed: {e}")
            sys.exit(1)

    print(f"✅ Got order history for date: {HISTORY_DATE or 'today'}")
    print(json.dumps(asdict(resp), indent=2, ensure_ascii=False))

    if resp.successful:
        orders = resp.data or []
        print(f"\n📋 Total orders returned: {len(orders)}")
        for i, order in enumerate(orders, 1):
            print(f"\n  Order #{i}")
            print(f"    Order ID     : {order.order_id}")
            print(f"    Instrument   : {order.instrument_id}")
            print(f"    Side         : {order.order_side.value}")
            print(f"    Status       : {order.order_status}")
            print(f"    Price        : {order.order_price}")
            print(f"    Total Qty    : {order.total_quantity}")
            print(f"    Executed Qty : {order.executed_quantity}")
            print(f"    Remaining    : {order.remaining_quantity}")
    elif resp.errors:
        print(f"\n📌 Errors ({len(resp.errors)}):")
        for err in resp.errors:
            print(f"   [{err.code}] ({err.type}) {err.message}")
    else:
        print("\n❌ Request was not successful.")


if __name__ == "__main__":
    asyncio.run(main())
