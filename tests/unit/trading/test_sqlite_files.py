"""SQLite directory checks (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.errors import ConfigurationError
from app.infrastructure.persistence import sqlite_files
from app.infrastructure.persistence.sqlite_files import ensure_writable_parent


def test_creates_missing_parent(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "trading.sqlite3"
    ensure_writable_parent(db)
    assert db.parent.is_dir()


def test_unwritable_directory_raises_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny(_path: object, _mode: int) -> bool:
        return False

    monkeypatch.setattr(sqlite_files.os, "access", deny)
    with pytest.raises(ConfigurationError, match="not writable"):
        ensure_writable_parent(tmp_path / "trading.sqlite3")
