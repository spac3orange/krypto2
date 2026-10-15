"""Wallet available-balance parsing for Isolated vs Cross margin."""

from __future__ import annotations

from decimal import Decimal

from app.infrastructure.bybit.gateway import settle_coin_available


def test_isolated_ignores_zero_account_available_and_uses_usdt_wallet() -> None:
    account = {
        "totalEquity": "183748.10",
        "totalAvailableBalance": "0",
        "coin": [
            {
                "coin": "USDT",
                "walletBalance": "100000",
                "totalPositionIM": "0",
                "totalOrderIM": "0",
                "locked": "0",
                "bonus": "0",
            }
        ],
    }
    assert settle_coin_available(
        account,
        settle_coin="USDT",
        margin_mode="ISOLATED_MARGIN",
    ) == Decimal("100000")


def test_isolated_subtracts_im_and_locked() -> None:
    account = {
        "totalAvailableBalance": "",
        "coin": [
            {
                "coin": "USDT",
                "walletBalance": "1000",
                "totalPositionIM": "200",
                "totalOrderIM": "50",
                "locked": "10",
                "bonus": "5",
            }
        ],
    }
    assert settle_coin_available(
        account,
        settle_coin="USDT",
        margin_mode="ISOLATED_MARGIN",
    ) == Decimal("735")


def test_cross_uses_account_total_available() -> None:
    account = {
        "totalAvailableBalance": "900.5",
        "coin": [
            {
                "coin": "USDT",
                "walletBalance": "1000",
                "totalPositionIM": "0",
                "totalOrderIM": "0",
                "locked": "0",
                "bonus": "0",
            }
        ],
    }
    assert settle_coin_available(
        account,
        settle_coin="USDT",
        margin_mode="REGULAR_MARGIN",
    ) == Decimal("900.5")


def test_cross_falls_back_to_coin_when_account_available_blank() -> None:
    account = {
        "totalAvailableBalance": "",
        "coin": [
            {
                "coin": "USDT",
                "walletBalance": "50",
                "totalPositionIM": "0",
                "totalOrderIM": "0",
                "locked": "0",
                "bonus": "0",
            }
        ],
    }
    assert settle_coin_available(
        account,
        settle_coin="USDT",
        margin_mode="REGULAR_MARGIN",
    ) == Decimal("50")
