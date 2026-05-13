"""Typed request/response models for Nibi's order-management endpoints.

Kept separate from `client.py` so the wire schema can be imported by
callers (scripts, arb engine, tests) without pulling in `requests` or
constructing a live session.

Convention: Python attribute names are snake_case; broker JSON keys are
camelCase. The `from_dict` / `from_response` classmethods do the
translation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OrderSide(StrEnum):
    """Side of an order on the Nibi `OrderEntry` endpoint.

    Values match the broker's `ISensOM` wire field exactly — keep the
    capitalisation, the broker rejects `"buy"` / `"sell"`.
    """

    BUY = "Buy"
    SELL = "Sell"


@dataclass(frozen=True, slots=True)
class Order:
    """One order record as returned by Nibi's order endpoints.

    Snake-case Python fields mirroring the broker's camelCase JSON.
    Construct via `Order.from_dict(d)` where `d` is the broker's `data`
    object (the inner dict, not the outer envelope).
    """

    id: int
    order_id: int
    principal_id: int
    principal_name: str
    created_by_id: int
    created_date: str
    order_status: str
    order_side: OrderSide
    flow: str
    market_type: str
    instrument_id: str
    ipo: bool
    is_option: bool
    c_size: int
    priority_datetime: str | None
    order_price: int
    total_quantity: int
    disclosed_quantity: int
    executed_quantity: int
    executed_price: float
    traded_value: float
    remaining_quantity: int
    validity_type: str
    validity_date: str | None
    error: str | None
    has_error: bool
    extra_info: Any | None
    modifying: bool
    commission_rate: float
    executed_by_id: int
    description: str | None
    option_strategy_unique_key: str | None
    parent_id: int | None
    investment_request_id: int | None
    connection_id: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Order:
        return cls(
            id=d["id"],
            order_id=d["orderId"],
            principal_id=d["principalId"],
            principal_name=d["principalName"],
            created_by_id=d["createdById"],
            created_date=d["createdDate"],
            order_status=d["orderStatus"],
            order_side=OrderSide(d["orderSide"]),
            flow=d["flow"],
            market_type=d["marketType"],
            instrument_id=d["instrumentId"],
            ipo=d["ipo"],
            is_option=d["isOption"],
            c_size=d["cSize"],
            priority_datetime=d["priorityDateTime"],
            order_price=d["orderPrice"],
            total_quantity=d["totalQuantity"],
            disclosed_quantity=d["disclosedQuantity"],
            executed_quantity=d["executedQuantity"],
            executed_price=d["executedPrice"],
            traded_value=d["tradedValue"],
            remaining_quantity=d["remainingQuantity"],
            validity_type=d["validityType"],
            validity_date=d["validityDate"],
            error=d["error"],
            has_error=d["hasError"],
            extra_info=d["extraInfo"],
            modifying=d["modifying"],
            commission_rate=d["commissionRate"],
            executed_by_id=d["executedById"],
            description=d["description"],
            option_strategy_unique_key=d["optionStrategyUniqueKey"],
            parent_id=d["parentId"],
            investment_request_id=d["investmentRequestId"],
            connection_id=d["connectionId"],
        )


@dataclass(frozen=True, slots=True)
class OrderError:
    """One structured error returned in the broker's `errors` list.

    Real-world example:

        {"message": "فروش کمتر از 5,000,000 ریال مقدور نیست. …",
         "type": "CustomException",
         "code": "LimitationComponentError"}

    `code` is the broker-defined identifier (stable, safe to branch on);
    `message` is the human-readable text (Persian, may change); `type`
    is the broker's internal exception class name.
    """

    message: str
    type: str
    code: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OrderError:
        return cls(
            message=d["message"],
            type=d["type"],
            code=d["code"],
        )


@dataclass(frozen=True, slots=True)
class CreateOrderResponse:
    """Envelope returned by `NibiBrokerClient.create_order`.

    Mirrors the broker's `{"response": {"successful", "count", "data",
    "errors"}}` wrapper. On success `data` is the placed `Order` and
    `errors` is `None`; on failure `data` is `None` and `errors` is a
    non-empty list of `OrderError`.
    """

    successful: bool
    data: Order | None
    errors: list[OrderError] | None
    count: int | None = None

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> CreateOrderResponse:
        r = payload["response"]
        raw_data = r.get("data")
        raw_errors = r.get("errors")
        return cls(
            successful=r["successful"],
            count=r.get("count"),
            data=Order.from_dict(raw_data) if raw_data is not None else None,
            errors=(
                [OrderError.from_dict(e) for e in raw_errors]
                if raw_errors is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class CancelOrderResponse:
    """Envelope returned by `NibiBrokerClient.cancel_order`.

    Structurally identical to `CreateOrderResponse` — the broker echoes
    the full `Order` state (with `orderStatus` reflecting the result of
    the cancellation request) under `data`. Kept as its own class so
    cancel-specific logic can be added later without touching create
    callers.
    """

    successful: bool
    data: Order | None
    errors: list[OrderError] | None
    count: int | None = None

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> CancelOrderResponse:
        r = payload["response"]
        raw_data = r.get("data")
        raw_errors = r.get("errors")
        return cls(
            successful=r["successful"],
            count=r.get("count"),
            data=Order.from_dict(raw_data) if raw_data is not None else None,
            errors=(
                [OrderError.from_dict(e) for e in raw_errors]
                if raw_errors is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class GetOrdersResponse:
    """Envelope returned by `NibiBrokerClient.get_orders`.

    Same outer wrapper as `CreateOrderResponse`, but `data` is a list
    of `Order` (the order book for the requested day) — empty list if
    no orders, `None` only on the failure path.
    """

    successful: bool
    data: list[Order] | None
    errors: list[OrderError] | None
    count: int | None = None

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> GetOrdersResponse:
        r = payload["response"]
        raw_data = r.get("data")
        raw_errors = r.get("errors")
        return cls(
            successful=r["successful"],
            count=r.get("count"),
            data=(
                [Order.from_dict(o) for o in raw_data]
                if raw_data is not None else None
            ),
            errors=(
                [OrderError.from_dict(e) for e in raw_errors]
                if raw_errors is not None else None
            ),
        )
