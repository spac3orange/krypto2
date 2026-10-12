"""Unit tests for Telegram client factory configuration."""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.telegram.client import create_telegram_client


def test_client_enables_auto_reconnect_and_sequential_updates(tmp_path: Path) -> None:
    session = tmp_path / "user"
    client = create_telegram_client(
        session_path=session,
        api_id=12345,
        api_hash="0123456789abcdef0123456789abcdef",
        catch_up=True,
        proxy_url="http://user:pass@127.0.0.1:8000",
    )
    try:
        assert client.session is not None
        # Public-ish constructor flags retained on the client instance
        assert client._auto_reconnect is True  # noqa: SLF001
        assert client._connection_retries is None  # noqa: SLF001 — infinite
        assert client._sequential_updates is True  # noqa: SLF001
        assert client._catch_up is True  # noqa: SLF001
        assert client._proxy is not None  # noqa: SLF001
        assert client._proxy["addr"] == "127.0.0.1"  # noqa: SLF001
    finally:
        client.session.close()
