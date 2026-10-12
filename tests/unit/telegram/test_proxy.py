"""Unit tests for PROXY_URL parsing."""

from __future__ import annotations

import pytest
from app.core.errors import ConfigurationError
from app.infrastructure.telegram.proxy import (
    parse_proxy_url,
    proxy_log_fields,
    proxy_url_for_aiogram,
)


def test_parse_http_proxy_with_auth() -> None:
    proxy = parse_proxy_url("http://user:pass@1.2.3.4:8000")
    assert proxy == {
        "proxy_type": "http",
        "addr": "1.2.3.4",
        "port": 8000,
        "username": "user",
        "password": "pass",
        "rdns": True,
    }


def test_parse_socks5_proxy() -> None:
    proxy = parse_proxy_url("socks5://1.2.3.4:1080")
    assert proxy["proxy_type"] == "socks5"
    assert proxy["username"] is None
    assert proxy["password"] is None


def test_parse_rejects_missing_port() -> None:
    with pytest.raises(ConfigurationError):
        parse_proxy_url("http://user:pass@1.2.3.4")


def test_aiogram_proxy_url_normalizes_scheme() -> None:
    assert proxy_url_for_aiogram("https://user:p%40ss@1.2.3.4:8000") == (
        "http://user:p%40ss@1.2.3.4:8000"
    )
    assert proxy_url_for_aiogram("socks5h://1.2.3.4:1080") == "socks5://1.2.3.4:1080"


def test_proxy_log_fields_omit_credentials() -> None:
    fields = proxy_log_fields("http://user:secret@1.2.3.4:8000")
    assert fields["proxy_enabled"] is True
    assert fields["proxy_host"] == "1.2.3.4"
    assert fields["proxy_port"] == 8000
    assert "user" not in str(fields)
    assert "secret" not in str(fields)
