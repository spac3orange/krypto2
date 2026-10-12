"""Telegram session path helpers."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_session_directory(session_path: Path) -> Path:
    """Ensure the parent directory for the session file exists.

    Best-effort restrictive permissions on POSIX; no-op failure on Windows.
    """
    # Telethon treats the path as a session *name* without `.session` suffix.
    # If path is `data/telegram/user`, parent is `data/telegram`.
    directory = session_path.parent
    directory.mkdir(parents=True, exist_ok=True)

    try:
        os.chmod(directory, stat.S_IRWXU)  # 0o700
    except OSError:
        logger.debug(
            "Could not tighten permissions on session directory",
            extra={"event": "telegram.session.permissions_skipped"},
        )
    return directory


def session_file_exists(session_path: Path) -> bool:
    """Return True if a Telethon SQLite session file is present."""
    candidate = Path(f"{session_path}.session")
    return candidate.is_file()
