"""File logging setup (no network)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.logging import log_event, setup_logging


def test_setup_logging_writes_app_and_errors(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    setup_logging("INFO", log_dir=log_dir)
    logger = logging.getLogger("test.logging")

    log_event(logger, logging.INFO, "test.info", "info line", symbol="BLUR")
    log_event(logger, logging.ERROR, "test.error", "error line", reason="boom")
    for handler in logging.getLogger().handlers:
        handler.flush()

    app_path = log_dir / "app.jsonl"
    err_path = log_dir / "errors.jsonl"
    assert app_path.is_file()
    assert err_path.is_file()

    app_lines = [json.loads(line) for line in app_path.read_text(encoding="utf-8").splitlines()]
    err_lines = [json.loads(line) for line in err_path.read_text(encoding="utf-8").splitlines()]

    assert any(row.get("event") == "test.info" and row.get("symbol") == "BLUR" for row in app_lines)
    assert any(row.get("event") == "test.error" for row in app_lines)
    assert any(row.get("event") == "test.error" for row in err_lines)
    assert all(row.get("level") in {"WARNING", "ERROR", "CRITICAL"} for row in err_lines)
    setup_logging("INFO", log_dir=None)


def test_setup_logging_can_skip_files() -> None:
    setup_logging("INFO", log_dir=None)
    assert any(isinstance(h, logging.StreamHandler) for h in logging.getLogger().handlers)
