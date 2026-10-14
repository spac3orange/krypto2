"""Standalone Bybit errors (no dependency on a host application)."""

from __future__ import annotations


class BybitError(Exception):
    """Base error for this package."""


class BybitTransportError(BybitError):
    """Network / SDK failure talking to Bybit."""


class BybitApiError(BybitError):
    """Bybit returned a non-zero retCode."""

    def __init__(self, ret_code: int | str, ret_msg: str) -> None:
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        super().__init__(f"bybit_api_error:{ret_code}")


class OrderUncertainError(BybitError):
    """Order create result is uncertain; reconcile by orderLinkId (do not retry blind)."""


class ExecutionTimeoutError(BybitError):
    """Timed out waiting for fill confirmation."""
