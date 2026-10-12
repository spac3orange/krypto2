"""Application processor: log Telegram events, parse signals, orchestrate trading."""

from __future__ import annotations

import logging

from app.application.notifications.null_notifier import NullOperatorNotifier
from app.application.trading.orchestrator import TradingSignalOrchestrator
from app.application.trading.signal_parser import TradingSignalParser
from app.core.logging import log_event
from app.domain.notifications.models import SignalNotice
from app.domain.notifications.ports import OperatorNotifier
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.models import TelegramMessageEvent
from app.domain.trading.models import ParsedTradingSignal

logger = logging.getLogger(__name__)


class LoggingMessageProcessor:
    """Consumes Telegram events: structured log + parse + optional orchestrator."""

    def __init__(
        self,
        *,
        log_message_text: bool = False,
        signal_parser: TradingSignalParser | None = None,
        orchestrator: TradingSignalOrchestrator | None = None,
        notifier: OperatorNotifier | None = None,
    ) -> None:
        self._log_message_text = log_message_text
        self._signal_parser = signal_parser or TradingSignalParser()
        self._orchestrator = orchestrator
        self._notifier = notifier or NullOperatorNotifier()

    async def process(self, event: TelegramMessageEvent) -> None:
        self._log_telegram_event(event)
        signal = self._parse_signal(event)
        if signal is None:
            return
        self._log_detected_signal(event, signal)
        await self._notify_signal(signal)
        if self._orchestrator is not None:
            await self._orchestrator.handle(event, signal)

    async def _notify_signal(self, signal: ParsedTradingSignal) -> None:
        notice = SignalNotice(
            symbol=signal.symbol,
            signal_type=signal.signal_type.value,
            action=signal.action.value,
            timeframe=signal.timeframe,
            change_percent=str(signal.change_percent),
            price_from=str(signal.price_from),
            price_to=str(signal.price_to),
        )
        try:
            await self._notifier.signal_detected(notice)
        except Exception as exc:  # noqa: BLE001 — notification must not stop parsing
            log_event(
                logger,
                logging.WARNING,
                "bot.notify.failed",
                "Signal notification failed",
                error_type=type(exc).__name__,
            )

    def _log_telegram_event(self, event: TelegramMessageEvent) -> None:
        event_name = (
            "telegram.message.edited"
            if event.event_type is TelegramEventType.MESSAGE_EDITED
            else "telegram.message.received"
        )
        fields: dict[str, object] = {
            "event_id": event.event_id,
            "chat_id": event.chat_id,
            "message_id": event.message_id,
            "event_type": event.event_type.value,
            "message_date": event.date.isoformat(),
            "text_length": len(event.text),
            "has_media": event.has_media,
            "reply_to_message_id": event.reply_to_message_id,
        }
        if self._log_message_text:
            fields["text"] = event.text

        log_event(
            logger,
            logging.INFO,
            event_name,
            "Telegram message event accepted by processor",
            **fields,
        )

    def _parse_signal(self, event: TelegramMessageEvent) -> ParsedTradingSignal | None:
        result = self._signal_parser.parse_detailed(event.text)
        if result.is_rejected:
            log_event(
                logger,
                logging.WARNING,
                "trading.signal.rejected",
                "Trading signal rejected due to incomplete or invalid format",
                event_id=event.event_id,
                chat_id=event.chat_id,
                message_id=event.message_id,
                telegram_event_type=event.event_type.value,
                reason=result.rejection_reason,
            )
            return None
        return result.signal

    def _log_detected_signal(
        self,
        event: TelegramMessageEvent,
        signal: ParsedTradingSignal,
    ) -> None:
        log_event(
            logger,
            logging.INFO,
            "trading.signal.detected",
            "Trading signal detected",
            event_id=event.event_id,
            chat_id=event.chat_id,
            message_id=event.message_id,
            telegram_event_type=event.event_type.value,
            exchange=signal.exchange,
            timeframe=signal.timeframe,
            symbol=signal.symbol,
            signal_type=signal.signal_type.value,
            action=signal.action.value,
            change_percent=str(signal.change_percent),
            price_from=str(signal.price_from),
            price_to=str(signal.price_to),
            signal_24h_count=signal.signal_24h_count,
        )
