"""Bybit preflight and unchanged TP/SL handling (no network)."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest
from app.application.trading.bootstrap import describe_preflight_failure
from app.core.errors import BybitApiError, BybitTransportError
from app.domain.trading.models import TakeProfitPlan
from app.infrastructure.bybit.gateway import BybitGateway
from pybit.exceptions import InvalidRequestError
from pybit.unified_trading import HTTP


class _UnchangedStop:
    def set_trading_stop(self, **kwargs: object) -> None:
        raise InvalidRequestError(
            request="POST /v5/position/trading-stop",
            message="not modified",
            status_code=34040,
            time="00:00:00",
            resp_headers=None,
        )


class _RejectedStop:
    def set_trading_stop(self, **kwargs: object) -> None:
        raise InvalidRequestError(
            request="POST /v5/position/trading-stop",
            message="params error",
            status_code=10001,
            time="00:00:00",
            resp_headers=None,
        )


def test_clock_skew_is_not_reported_as_invalid_key() -> None:
    reason, message = describe_preflight_failure(BybitApiError(10002, "timestamp"))
    assert reason == "clock_skew"
    assert "10002" in message
    assert "API key" not in message


def test_invalid_key_code_stays_invalid_key() -> None:
    reason, message = describe_preflight_failure(BybitApiError(10003, "API key is invalid."))
    assert reason == "api_key_invalid"
    assert "API key" in message


def test_transport_failure_is_generic_preflight() -> None:
    reason, _message = describe_preflight_failure(BybitTransportError("timeout"))
    assert reason == "preflight_failed"


@pytest.mark.asyncio
async def test_unchanged_take_profit_is_success() -> None:
    gateway = BybitGateway(cast(HTTP, _UnchangedStop()), demo=True)
    await gateway.set_trading_stop(
        symbol="DOGEUSDT",
        plan=TakeProfitPlan(
            take_profit_price=Decimal("0.08768"),
            stop_loss_price=Decimal("0.08339"),
            tp_trigger_by="LastPrice",
            sl_trigger_by="LastPrice",
        ),
    )


@pytest.mark.asyncio
async def test_other_trading_stop_error_is_raised() -> None:
    gateway = BybitGateway(cast(HTTP, _RejectedStop()), demo=True)
    with pytest.raises(BybitApiError) as exc:
        await gateway.set_trading_stop(
            symbol="DOGEUSDT",
            plan=TakeProfitPlan(
                take_profit_price=Decimal("1"),
                stop_loss_price=Decimal("1"),
                tp_trigger_by="LastPrice",
            ),
        )
    assert str(exc.value.ret_code) == "10001"
