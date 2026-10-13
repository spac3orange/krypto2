"""SQLite durable execution journal."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.core.errors import ExecutionConflictError
from app.domain.trading.enums import ExecutionStatus
from app.domain.trading.models import ExecutionRecord
from app.infrastructure.persistence.sqlite_files import ensure_writable_parent


def _dec(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _dec_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


class SqliteExecutionStore:
    """Thread-safe SQLite execution store (stdlib sqlite3)."""

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
                CREATE TABLE IF NOT EXISTS executions (
                    event_id TEXT PRIMARY KEY,
                    order_link_id TEXT NOT NULL UNIQUE,
                    correlation_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    qty TEXT,
                    target_margin TEXT,
                    target_notional TEXT,
                    bybit_order_id TEXT,
                    avg_price TEXT,
                    take_profit_price TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_by_event_id(self, event_id: str) -> ExecutionRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_order_link_id(self, order_link_id: str) -> ExecutionRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE order_link_id = ?",
                (order_link_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def reserve(
        self,
        *,
        event_id: str,
        order_link_id: str,
        correlation_id: str,
        symbol: str,
        side: str,
    ) -> ExecutionRecord:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO executions (
                        event_id, order_link_id, correlation_id, symbol, side, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        order_link_id,
                        correlation_id,
                        symbol,
                        side,
                        ExecutionStatus.RESERVED.value,
                        now,
                        now,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ExecutionConflictError(f"event already reserved: {event_id}") from exc
        record = self.get_by_event_id(event_id)
        assert record is not None
        return record

    def update(
        self,
        event_id: str,
        *,
        status: ExecutionStatus,
        qty: Decimal | None = None,
        target_margin: Decimal | None = None,
        target_notional: Decimal | None = None,
        bybit_order_id: str | None = None,
        avg_price: Decimal | None = None,
        take_profit_price: Decimal | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ExecutionRecord:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                msg = f"execution not found: {event_id}"
                raise KeyError(msg)
            conn.execute(
                """
                UPDATE executions SET
                    status = ?,
                    qty = COALESCE(?, qty),
                    target_margin = COALESCE(?, target_margin),
                    target_notional = COALESCE(?, target_notional),
                    bybit_order_id = COALESCE(?, bybit_order_id),
                    avg_price = COALESCE(?, avg_price),
                    take_profit_price = COALESCE(?, take_profit_price),
                    error_code = COALESCE(?, error_code),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE event_id = ?
                """,
                (
                    status.value,
                    _dec_str(qty),
                    _dec_str(target_margin),
                    _dec_str(target_notional),
                    bybit_order_id,
                    _dec_str(avg_price),
                    _dec_str(take_profit_price),
                    error_code,
                    error_message,
                    now,
                    event_id,
                ),
            )
            conn.commit()
        record = self.get_by_event_id(event_id)
        assert record is not None
        return record

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ExecutionRecord:
        return ExecutionRecord(
            event_id=row["event_id"],
            order_link_id=row["order_link_id"],
            correlation_id=row["correlation_id"],
            symbol=row["symbol"],
            side=row["side"],
            status=ExecutionStatus(row["status"]),
            qty=_dec(row["qty"]),
            target_margin=_dec(row["target_margin"]),
            target_notional=_dec(row["target_notional"]),
            bybit_order_id=row["bybit_order_id"],
            avg_price=_dec(row["avg_price"]),
            take_profit_price=_dec(row["take_profit_price"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
