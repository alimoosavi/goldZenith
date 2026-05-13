"""Place a single order via the Nibi broker REST API.

Edit the order params at the top of this file, then:

    uv run python scripts/create_order.py

Auth + endpoint come from `config` (NIBI_AUTH_TOKEN, NIBI_COOKIE,
NIBI_RED_ENDPOINT_BASE_URL in `.env`).
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict

import aiohttp

from broker.nibi import NibiBrokerClient, OrderSide
from settings import config

# ── Order params ─────────────────────────────────────────────────────────────
INSTRUMENT_ID      = "IRTKMOFD0001"
SIDE               = OrderSide.BUY  # OrderSide.BUY | OrderSide.SELL
PRICE              = 550_000
QUANTITY           = 1
VALIDITY           = "Day"
VALIDITY_DATE      = None
DISCLOSED_QUANTITY = 0
EXECUTION_TYPE     = "Instant"


async def main() -> None:
    async with NibiBrokerClient(
        auth_token=config.nibi_auth_token,
        cookie=config.nibi_cookie,
        red_endpoint_base_url=config.nibi_red_endpoint_base_url,
    ) as client:
        try:
            resp = await client.create_order(
                instrument_id=INSTRUMENT_ID,
                side=SIDE,
                price=PRICE,
                quantity=QUANTITY,
                validity=VALIDITY,
                validity_date=VALIDITY_DATE,
                disclosed_quantity=DISCLOSED_QUANTITY,
                execution_type=EXECUTION_TYPE,
            )
        except aiohttp.ClientResponseError as e:
            print(f"❌ HTTP Error: {e.status} - {e.message}")
            sys.exit(1)
        except aiohttp.ClientConnectionError:
            print("❌ Connection Error: Could not reach the endpoint.")
            sys.exit(1)
        except aiohttp.ClientError as e:
            print(f"❌ Request failed: {e}")
            sys.exit(1)

    print("✅ Success!" if resp.successful else "❌ Failed!")
    print(json.dumps(asdict(resp), indent=2, ensure_ascii=False))

    if resp.successful and resp.data is not None:
        order = resp.data
        print(f"\n📌 Order ID     : {order.order_id}")
        print(f"📌 Order Status : {order.order_status}")
        print(f"📌 Order Side   : {order.order_side.value}")
        print(f"📌 Instrument   : {order.instrument_id}")
    elif resp.errors:
        print(f"\n📌 Errors ({len(resp.errors)}):")
        for err in resp.errors:
            print(f"   [{err.code}] ({err.type}) {err.message}")


if __name__ == "__main__":
    asyncio.run(main())
