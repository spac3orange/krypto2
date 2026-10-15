"""Shared mutable deps for operator-bot handlers."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.trading.runtime_config_service import RuntimeConfigService
from app.domain.trading.ports import TradingGateway


@dataclass
class OperatorBotDeps:
    """Config is required; exchange gateway is attached after trading preflight."""

    config: RuntimeConfigService
    gateway: TradingGateway | None = None
    trading_mode: str = "disabled"
