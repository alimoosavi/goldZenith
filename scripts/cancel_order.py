"""Cancel a single order by ID via the Nibi broker REST API.

Edit ORDER_ID below, then:

    uv run python scripts/cancel_order.py

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

# ── Order to cancel ──────────────────────────────────────────────────────────
ORDER_ID = 978151


async def main() -> None:
    async with NibiBrokerClient(
        auth_token=config.nibi_auth_token,
        cookie=config.nibi_cookie,
        red_endpoint_base_url=config.nibi_red_endpoint_base_url,
    ) as client:
        try:
            resp = await client.cancel_order(order_id=ORDER_ID)
        except aiohttp.ClientResponseError as e:
            print(f"❌ HTTP Error: {e.status} - {e.message}")
            sys.exit(1)
        except aiohttp.ClientConnectionError:
            print("❌ Connection Error: Could not reach the endpoint.")
            sys.exit(1)
        except aiohttp.ClientError as e:
            print(f"❌ Request failed: {e}")
            sys.exit(1)

    print("✅ Cancellation request sent!")
    print(json.dumps(asdict(resp), indent=2, ensure_ascii=False))

    if resp.successful:
        print(f"\n📌 Order {ORDER_ID} cancelled successfully.")
        if resp.data is not None:
            order = resp.data
            print(f"    Status       : {order.order_status}")
            print(f"    Remaining    : {order.remaining_quantity}/{order.total_quantity}")
    elif resp.errors:
        print(f"\n📌 Errors ({len(resp.errors)}):")
        for err in resp.errors:
            print(f"   [{err.code}] ({err.type}) {err.message}")
    else:
        print("\n❌ Cancellation was not successful.")


if __name__ == "__main__":
    asyncio.run(main())
