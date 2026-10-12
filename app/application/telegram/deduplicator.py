"""In-memory bounded event deduplicator."""

from __future__ import annotations

from collections import OrderedDict


class InMemoryEventDeduplicator:
    """LRU-ish set of recently seen event IDs."""

    def __init__(self, *, max_size: int = 10_000) -> None:
        if max_size < 1:
            msg = "max_size must be >= 1"
            raise ValueError(msg)
        self._max_size = max_size
        self._seen: OrderedDict[str, None] = OrderedDict()

    def seen(self, event_id: str) -> bool:
        """Return True if already seen; otherwise recorxd and return False."""
        if event_id in self._seen:
            self._seen.move_to_end(event_id)
            return True
        self._seen[event_id] = None
        if len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return False
