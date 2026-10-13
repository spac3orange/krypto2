"""Filesystem checks shared by the SQLite stores."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.errors import ConfigurationError


def ensure_writable_parent(path: Path) -> None:
    """Create the parent directory and fail clearly if it is not writable."""
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"Cannot create directory for SQLite database: {directory}"
        raise ConfigurationError(msg) from exc
    if not os.access(directory, os.W_OK | os.X_OK):
        msg = (
            f"SQLite directory is not writable: {directory}. "
            f"Process uid={_uid()} needs write access (Docker: chown the mounted host folder)."
        )
        raise ConfigurationError(msg)
    if path.exists() and not os.access(path, os.R_OK | os.W_OK):
        msg = f"SQLite file is not writable: {path}. Process uid={_uid()}."
        raise ConfigurationError(msg)


def _uid() -> str:
    getuid = getattr(os, "getuid", None)
    return str(getuid()) if getuid is not None else "n/a"
