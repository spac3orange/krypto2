"""Signal validation before execution (no exchange I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.errors import SignalValidationError
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.models import TelegramMessageEvent
from app.domain.trading.models import ParsedTradingSignal
from app.domain.trading.runtime_config import RuntimeConfigSource


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Result of validating a parsed signal against policy."""

    ok: bool
    reason: str | None = None


class SignalValidator:
    """Validates transport metadata + parsed signal for execution eligibility."""

    def __init__(self, config: RuntimeConfigSource) -> None:
        self._config = config

    def validate(
        self,
        event: TelegramMessageEvent,
        signal: ParsedTradingSignal,
        *,
        now: datetime | None = None,
    ) -> ValidationOutcome:
        if (
            event.event_type is TelegramEventType.MESSAGE_EDITED
            and not self._config.get().execute_edited_messages
        ):
            return ValidationOutcome(ok=False, reason="edited_message")

        if signal.exchange.upper() != "BYBIT":
            return ValidationOutcome(ok=False, reason="unsupported_exchange")

        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        message_date = event.date
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=UTC)
        age = (current - message_date.astimezone(UTC)).total_seconds()
        if age > self._config.get().max_signal_age_seconds:
            return ValidationOutcome(ok=False, reason="stale_signal")
        if age < -5:
            # Clock skew tolerance; large future dates are suspicious.
            return ValidationOutcome(ok=False, reason="invalid_message_date")

        if signal.symbol.strip() == "":
            return ValidationOutcome(ok=False, reason="missing_symbol")

        return ValidationOutcome(ok=True)

    def validate_or_raise(
        self,
        event: TelegramMessageEvent,
        signal: ParsedTradingSignal,
        *,
        now: datetime | None = None,
    ) -> None:
        outcome = self.validate(event, signal, now=now)
        if not outcome.ok:
            raise SignalValidationError(outcome.reason or "invalid_signal")
