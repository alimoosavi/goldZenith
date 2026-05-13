"""Async HTTPS client for Nibi's order-management REST API (`red.nibi.ir`).

Wraps the three OMS endpoints — `OrderEntry`, `OrderCancellation`,
`GetOrders` — behind a single async class. Backed by aiohttp so it
shares an event loop cleanly with `NibiStreamer` (also asyncio) and
plays nicely with the arb engine's async control flow.

Wire schema (`OrderSide`, `Order`, `OrderError`, ...Response) lives in
`schema.py` so callers can import the typed payloads without pulling
in aiohttp or constructing a live session.

Usage:

    import asyncio
    from broker.nibi import NibiBrokerClient, OrderSide
    from settings import config

    async def main() -> None:
        async with NibiBrokerClient(
            auth_token=config.nibi_auth_token,
            cookie=config.nibi_cookie,
            red_endpoint_base_url=config.nibi_red_endpoint_base_url,
        ) as client:
            res = await client.create_order(
                instrument_id="IRTKMOFD0001",
                side=OrderSide.BUY,
                price=561_000,
                quantity=2,
            )
            if res.successful and res.data is not None:
                await client.cancel_order(order_id=res.data.order_id)
            await client.get_orders()

    asyncio.run(main())

The underlying `aiohttp.ClientSession` is created lazily on the first
call and torn down via the async context manager (preferred) or an
explicit `await client.close()`. HTTP-level failures raise
`aiohttp.ClientResponseError` from `raise_for_status()`.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType

import aiohttp

from .schema import (
    CancelOrderResponse,
    CreateOrderResponse,
    GetOrdersResponse,
    OrderSide,
)


class NibiBrokerClient:
    """Async order-management client for the Nibi broker (`red.nibi.ir`).

    `auth_token` and `cookie` are session-bound — when they expire the
    client must be reconstructed with fresh credentials (the streamer's
    auth pair works here too; both endpoints share the same session
    headers).

    `red_endpoint_base_url` is injected by the caller (typically from
    `config.nibi_red_endpoint_base_url`) — the client itself stays
    decoupled from the settings module so it can be used in tests or
    against staging without touching env vars.

    Prefer the async-context-manager form so the session is closed even
    on exception; the manual `await client.close()` path is provided
    for cases where the client outlives a single `async with` block
    (long-running arb engine, etc.).
    """

    def __init__(
        self,
        auth_token: str,
        cookie: str,
        *,
        red_endpoint_base_url: str,
        timeout: float = 10.0,
        verify_ssl: bool = True,
    ) -> None:
        if not auth_token:
            raise ValueError("NibiBrokerClient: auth_token is empty")
        if not cookie:
            raise ValueError("NibiBrokerClient: cookie is empty")
        if not red_endpoint_base_url:
            raise ValueError("NibiBrokerClient: red_endpoint_base_url is empty")
        self.red_endpoint_base_url = red_endpoint_base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.verify_ssl = verify_ssl
        self._headers = {
            "Authorization": auth_token,
            "Cookie": cookie,
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    async def __aenter__(self) -> NibiBrokerClient:
        await self._ensure_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying aiohttp session. Idempotent — safe to
        call repeatedly and safe to call before any request has been
        issued (no-op in that case)."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Lazily create the aiohttp session on first use. The session
        carries the shared `Authorization` / `Cookie` / `Content-Type`
        headers and the configured timeout / SSL policy so each request
        method stays a clean one-liner."""
        if self._session is None or self._session.closed:
            # `ssl=False` disables verification entirely; `ssl=None`
            # falls back to aiohttp's default (verify with system CAs).
            connector = aiohttp.TCPConnector(
                ssl=None if self.verify_ssl else False,
            )
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=self.timeout,
                connector=connector,
            )
        return self._session

    # ── endpoints ────────────────────────────────────────────────────────

    async def create_order(
        self,
        *,
        instrument_id: str,
        side: OrderSide,
        price: int,
        quantity: int,
        validity: str = "Day",
        validity_date: str | None = None,
        disclosed_quantity: int = 0,
        execution_type: str = "Instant",
    ) -> CreateOrderResponse:
        """POST `/api/Orders/OrderEntry`.

        Returns a `CreateOrderResponse` — check `.successful`, then
        read `.data` (the placed `Order`) or `.errors` accordingly.

        `side` is an `OrderSide` enum (`OrderSide.BUY` / `OrderSide.SELL`).
        `validity` is the broker's `YValiOmNSC` (e.g. `"Day"`);
        `validity_date` (`DValiOM`) is only meaningful for date-validity
        orders. `disclosed_quantity` (`QTitDvlOM`) is the iceberg
        disclosed size — `0` = full quantity visible.
        """
        payload = {
            "InstrumentId": instrument_id,
            "ISensOM": side.value,
            "YValiOmNSC": validity,
            "DValiOM": validity_date,
            "PLimSaiOM": price,
            "QTitTotOM": quantity,
            "QTitDvlOM": disclosed_quantity,
            "ExecutionType": execution_type,
        }
        session = await self._ensure_session()
        async with session.post(
            f"{self.red_endpoint_base_url}/api/Orders/OrderEntry",
            json=payload,
        ) as r:
            r.raise_for_status()
            data = await r.json()
            return CreateOrderResponse.from_response(data)

    async def cancel_order(self, order_id: int) -> CancelOrderResponse:
        """POST `/api/Orders/OrderCancellation?orderId=<id>` (no body).

        Returns a `CancelOrderResponse` — check `.successful`, then read
        `.data` (the `Order` echoed back by the broker, with
        `order_status` updated to reflect the cancellation result) or
        `.errors`.
        """
        session = await self._ensure_session()
        async with session.post(
            f"{self.red_endpoint_base_url}/api/Orders/OrderCancellation",
            params={"orderId": order_id},
        ) as r:
            r.raise_for_status()
            data = await r.json()
            return CancelOrderResponse.from_response(data)

    async def get_orders(
        self,
        history_date: str | None = None,
    ) -> GetOrdersResponse:
        """GET `/api/Orders/GetOrders?historyDate=YYYYMMDD`.

        Returns a `GetOrdersResponse` — check `.successful`, then read
        `.data` (a list of `Order`) or `.errors`. `history_date` is
        `"YYYYMMDD"`; `None` defaults to today's date in the local
        timezone (matches the original script's behaviour).
        """
        if history_date is None:
            history_date = datetime.now().strftime("%Y%m%d")
        session = await self._ensure_session()
        async with session.get(
            f"{self.red_endpoint_base_url}/api/Orders/GetOrders",
            params={"historyDate": history_date},
        ) as r:
            r.raise_for_status()
            data = await r.json()
            return GetOrdersResponse.from_response(data)
