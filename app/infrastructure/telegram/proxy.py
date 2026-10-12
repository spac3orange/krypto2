"""Parse PROXY_URL into a Telethon-compatible proxy dict."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, unquote, urlparse

from app.core.errors import ConfigurationError

_SUPPORTED_SCHEMES = {
    "http": "http",
    "https": "http",
    "socks4": "socks4",
    "socks5": "socks5",
    "socks5h": "socks5",
}


def parse_proxy_url(proxy_url: str) -> dict[str, Any]:
    """Convert ``scheme://user:pass@host:port`` into Telethon proxy kwargs.

    Credentials are kept only in the returned dict for Telethon; callers MUST
    never log this dict or the original URL.
    """
    cleaned = proxy_url.strip()
    if not cleaned:
        msg = "PROXY_URL is empty"
        raise ConfigurationError(msg)

    parsed = urlparse(cleaned)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _SUPPORTED_SCHEMES:
        msg = "PROXY_URL scheme must be one of: http, https, socks4, socks5, socks5h"
        raise ConfigurationError(msg)

    if not parsed.hostname:
        msg = "PROXY_URL must include a hostname"
        raise ConfigurationError(msg)
    if parsed.port is None:
        msg = "PROXY_URL must include an explicit port"
        raise ConfigurationError(msg)

    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None

    return {
        "proxy_type": _SUPPORTED_SCHEMES[scheme],
        "addr": parsed.hostname,
        "port": int(parsed.port),
        "username": username,
        "password": password,
        "rdns": True,
    }


def proxy_url_for_aiogram(proxy_url: str) -> str:
    """Normalize ``PROXY_URL`` for aiogram (``https`` → ``http``, ``socks5h`` → ``socks5``)."""
    parsed = parse_proxy_url(proxy_url)
    auth = ""
    username = parsed["username"]
    password = parsed["password"]
    if isinstance(username, str) and username:
        auth = quote(username, safe="")
        if isinstance(password, str) and password:
            auth = f"{auth}:{quote(password, safe='')}"
        auth = f"{auth}@"
    return f"{parsed['proxy_type']}://{auth}{parsed['addr']}:{parsed['port']}"


def proxy_log_fields(proxy_url: str | None) -> dict[str, object]:
    """Safe fields for structured logs (no credentials)."""
    if not proxy_url:
        return {"proxy_enabled": False}
    parsed = urlparse(proxy_url.strip())
    host = parsed.hostname or "unknown"
    port = parsed.port or "unknown"
    return {
        "proxy_enabled": True,
        "proxy_scheme": (parsed.scheme or "unknown").lower(),
        "proxy_host": host,
        "proxy_port": port,
    }
