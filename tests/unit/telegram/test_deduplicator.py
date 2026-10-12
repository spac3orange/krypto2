"""Unit tests for in-memory deduplicator."""

from __future__ import annotations

from app.application.telegram.deduplicator import InMemoryEventDeduplicator


def test_first_seen_returns_false_then_true() -> None:
    dedup = InMemoryEventDeduplicator(max_size=3)
    assert dedup.seen("a") is False
    assert dedup.seen("a") is True


def test_evicts_oldest_when_over_capacity() -> None:
    dedup = InMemoryEventDeduplicator(max_size=2)
    assert dedup.seen("a") is False
    assert dedup.seen("b") is False
    assert dedup.seen("c") is False
    # "a" should have been evicted
    assert dedup.seen("a") is False
    assert dedup.seen("c") is True
