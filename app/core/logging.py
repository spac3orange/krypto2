"""Structured JSON logging to stdout and a dedicated logs folder."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "event",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", None),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if payload.get("event") is None:
            del payload["event"]
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    *,
    log_dir: Path | None = Path("logs"),
    retain_days: int = 14,
) -> Path | None:
    """Configure root logger: stdout + rotating files under ``log_dir``.

    Files (JSON lines, one event per line):
      - ``app.jsonl`` — all messages at ``level`` and above
      - ``errors.jsonl`` — WARNING / ERROR / CRITICAL only (easier triage)

    Returns the log directory path, or ``None`` when file logging is disabled.
    """
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    formatter = JsonFormatter()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    stream.setLevel(level.upper())
    root.addHandler(stream)

    resolved: Path | None = None
    if log_dir is not None:
        resolved = Path(log_dir)
        resolved.mkdir(parents=True, exist_ok=True)

        app_handler = TimedRotatingFileHandler(
            resolved / "app.jsonl",
            when="midnight",
            interval=1,
            backupCount=max(retain_days, 1),
            encoding="utf-8",
            utc=True,
        )
        app_handler.setFormatter(formatter)
        app_handler.setLevel(level.upper())
        app_handler.suffix = "%Y-%m-%d"
        root.addHandler(app_handler)

        error_handler = TimedRotatingFileHandler(
            resolved / "errors.jsonl",
            when="midnight",
            interval=1,
            backupCount=max(retain_days, 1),
            encoding="utf-8",
            utc=True,
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.WARNING)
        error_handler.suffix = "%Y-%m-%d"
        root.addHandler(error_handler)

    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    return resolved


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    """Emit a structured log with a stable `event` name."""
    logger.log(level, message, extra={"event": event, **fields})
