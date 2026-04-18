"""In-memory frontier helpers; durable state lives in SQLite (TODO)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class FrontierTask:
    url: str
    origin_url: str
    depth: int
    discovered_from: str | None


class InMemoryFrontier:
    """Optional helper for tests; production path should prefer DB frontier rows."""

    def __init__(self) -> None:
        self._q: deque[FrontierTask] = deque()

    def push(self, task: FrontierTask) -> None:
        # TODO: optional depth / duplicate checks before enqueue.
        self._q.append(task)

    def pop(self) -> FrontierTask | None:
        if not self._q:
            return None
        return self._q.popleft()
