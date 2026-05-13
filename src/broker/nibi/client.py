"""Sync HTTPS client for Nibi's order-management REST API (`red.nibi.ir`).

Wraps the three OMS endpoints — `OrderEntry`, `OrderCancellation`,
`GetOrders` — behind a single class so callers don't repeat the
`Authorization` / `Cookie` / `Content-Type` headers and base-URL
plumbing per call.

Wire schema (`OrderSide`, `Order`, `OrderError`, `CreateOrderResponse`,
`CancelOrderResponse`, `GetOrdersResponse`) lives in `schema.py` so
callers can import the typed payloads without pulling in `requests` or
constructing a live session.

Usage:

    from broker.nibi import NibiBrokerClient, OrderSide
    from settings import config

    client = NibiBrokerClient(
        auth_token=config.nibi_auth_token,
        cookie=config.nibi_cookie,
        red_endpoint_base_url=config.nibi_red_endpoint_base_url,
    )
    res = client.create_order(
        instrument_id="IRTKMOFD0001",
        side=OrderSide.BUY,
        price=561_000,
        quantity=2,
    )
    if res.successful and res.data is not None:
        client.cancel_order(order_id=res.data.order_id)
    client.get_orders()                # today
    client.get_orders("20250226")      # explicit date

HTTP-level failures raise `requests.HTTPError`.
"""

from __future__ import annotations

from datetime import datetime

import requests

from .schema import (
    CancelOrderResponse,
    CreateOrderResponse,
    GetOrdersResponse,
    OrderSide,
)


class NibiBrokerClient:
    """Order-management client for the Nibi broker (`red.nibi.ir`).

    `auth_token` and `cookie` are session-bound — when they expire the
    client must be reconstructed with fresh credentials (the streamer's
    auth pair works here too; both endpoints share the same session
    headers).

    `red_endpoint_base_url` is injected by the caller (typically from
    `config.nibi_red_endpoint_base_url`) — the client itself stays
    decoupled from the settings module so it can be used in tests or
    against staging without touching env vars.
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
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._headers = {
            "Authorization": auth_token,
            "Cookie": cookie,
            "Content-Type": "application/json",
        }
        self._session = requests.Session()

    # ── endpoints ────────────────────────────────────────────────────────

    def create_order(
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
        r = self._session.post(
            f"{self.red_endpoint_base_url}/api/Orders/OrderEntry",
            headers=self._headers,
            json=payload,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        return CreateOrderResponse.from_response(r.json())

    def cancel_order(self, order_id: int) -> CancelOrderResponse:
        """POST `/api/Orders/OrderCancellation?orderId=<id>` (no body).

        Returns a `CancelOrderResponse` — check `.successful`, then read
        `.data` (the `Order` echoed back by the broker, with
        `order_status` updated to reflect the cancellation result) or
        `.errors`.
        """
        r = self._session.post(
            f"{self.red_endpoint_base_url}/api/Orders/OrderCancellation",
            headers=self._headers,
            params={"orderId": order_id},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        return CancelOrderResponse.from_response(r.json())

    def get_orders(self, history_date: str | None = None) -> GetOrdersResponse:
        """GET `/api/Orders/GetOrders?historyDate=YYYYMMDD`.

        Returns a `GetOrdersResponse` — check `.successful`, then read
        `.data` (a list of `Order`) or `.errors`. `history_date` is
        `"YYYYMMDD"`; `None` defaults to today's date in the local
        timezone (matches the original script's behaviour).
        """
        if history_date is None:
            history_date = datetime.now().strftime("%Y%m%d")
        r = self._session.get(
            f"{self.red_endpoint_base_url}/api/Orders/GetOrders",
            headers=self._headers,
            params={"historyDate": history_date},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        return GetOrdersResponse.from_response(r.json())
