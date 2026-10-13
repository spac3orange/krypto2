"""SQLite key/value store for runtime trading config."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.infrastructure.persistence.sqlite_files import ensure_writable_parent


class SqliteRuntimeConfigStore:
    """Table ``runtime_config`` in the trading SQLite file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        ensure_writable_parent(self._path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_all(self) -> dict[str, str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM runtime_config").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def put_many(self, values: dict[str, str]) -> None:
        if not values:
            return
        now = datetime.now(UTC).isoformat()
        rows = [(key, value, now) for key, value in values.items()]
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO runtime_config (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            conn.commit()
