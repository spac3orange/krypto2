"""Resolve raw ticker symbols to Bybit linear USDT perpetuals."""

from __future__ import annotations

from app.core.errors import InstrumentConstraintError, InstrumentNotFoundError
from app.domain.trading.models import ResolvedInstrument
from app.domain.trading.ports import TradingGateway


class BybitInstrumentResolver:
    """Maps parser symbols (e.g. SAGA) → SAGAUSDT linear USDT perpetual."""

    def __init__(
        self,
        gateway: TradingGateway,
        *,
        settle_coin: str = "USDT",
        quote_suffix: str = "USDT",
    ) -> None:
        self._gateway = gateway
        self._settle_coin = settle_coin.upper()
        self._quote_suffix = quote_suffix.upper()

    def candidate_symbol(self, raw_symbol: str) -> str:
        symbol = raw_symbol.strip().upper()
        if symbol.endswith(self._quote_suffix):
            return symbol
        return f"{symbol}{self._quote_suffix}"

    async def resolve(self, raw_symbol: str) -> ResolvedInstrument:
        candidate = self.candidate_symbol(raw_symbol)
        instrument = await self._gateway.get_instrument(candidate)
        if instrument is None:
            raise InstrumentNotFoundError(candidate)
        if instrument.status != "Trading":
            raise InstrumentConstraintError("instrument_not_trading")
        if instrument.settle_coin.upper() != self._settle_coin:
            raise InstrumentConstraintError("unexpected_settle_coin")
        if instrument.quote_coin.upper() != self._quote_suffix:
            raise InstrumentConstraintError("unexpected_quote_coin")
        return instrument
