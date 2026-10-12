"""Opt-in Bybit Demo Trading smoke tests (skipped by default)."""

from __future__ import annotations

import os

import pytest


@pytest.mark.bybit_demo
@pytest.mark.skipif(
    os.getenv("RUN_BYBIT_DEMO") != "1",
    reason="Set RUN_BYBIT_DEMO=1 with Demo Trading keys to enable",
)
def test_bybit_demo_placeholder() -> None:
    """Manual/opt-in marker — real network calls not run in default CI."""
    assert os.getenv("BYBIT_API_KEY")
    assert os.getenv("BYBIT_API_SECRET")
