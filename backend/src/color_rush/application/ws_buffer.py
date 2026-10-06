from __future__ import annotations

from collections import deque
from typing import Any

from color_rush.observability.metrics import SNAPSHOT_COALESCED, SNAPSHOT_DROPPED

MAX_BUFFER = 8


class SnapshotClientBuffer:
    """Bounded per-client snapshot queue. Coalesce superseded count snapshots; never grow unbounded."""

    def __init__(self, max_size: int = MAX_BUFFER) -> None:
        self.max_size = max_size
        self._q: deque[dict[str, Any]] = deque()
        self.dropped = 0
        self.coalesced = 0

    def push(self, snapshot: dict[str, Any]) -> None:
        seq = int(snapshot.get("snapshot_sequence") or 0)
        if self._q:
            last_seq = int(self._q[-1].get("snapshot_sequence") or 0)
            if seq < last_seq:
                return
            if seq == last_seq:
                self._q[-1] = snapshot
                return
        if len(self._q) >= self.max_size:
            self._q.popleft()
            self.coalesced += 1
            SNAPSHOT_COALESCED.inc()
            if len(self._q) >= self.max_size:
                self._q.clear()
                self.dropped += 1
                SNAPSHOT_DROPPED.inc()
        self._q.append(snapshot)

    def pop_send(self) -> dict[str, Any] | None:
        if not self._q:
            return None
        if len(self._q) > 1:
            skipped = len(self._q) - 1
            self.coalesced += skipped
            SNAPSHOT_COALESCED.inc(skipped)
            latest = self._q[-1]
            self._q.clear()
            return latest
        return self._q.popleft()
