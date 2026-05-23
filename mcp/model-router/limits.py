"""In-memory circuit breaker and rate limiter for model-router.

>>> breaker = CircuitBreaker(threshold=2, window_seconds=60)
>>> breaker.record_reject("coder", "change-1") is None
True
>>> breaker.is_open("coder", "change-1")
False
>>> breaker.record_reject("coder", "change-1").severity
'SEV-2'
>>> breaker.is_open("coder", "change-1")
True
>>> breaker.reset("coder", "change-1")
>>> breaker.is_open("coder", "change-1")
False
>>> limiter = RateLimiter(qps=2)
>>> limiter.acquire("coder", "gpt-5")
True
>>> limiter.acquire("coder", "gpt-5")
True
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from dataclasses import dataclass

MAX_ACTIVE_KEYS = 1000


@dataclass(frozen=True)
class CircuitEvent:
    agent_role: str
    change_id: str
    severity: str
    reason: str


class CircuitBreaker:
    def __init__(self, threshold: int = 5, window_seconds: int = 60) -> None:
        self.threshold = threshold
        self.window_seconds = window_seconds
        self._rejects: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()

    def record_reject(self, agent_role: str, change_id: str) -> CircuitEvent | None:
        key = (agent_role, change_id)
        bucket = self._rejects.get(key)
        if bucket is None:
            bucket = deque()
            self._rejects[key] = bucket
        self._rejects.move_to_end(key)
        now = time.monotonic()
        self._prune(bucket, now)
        bucket.append(now)
        self._evict_if_needed()
        return (
            CircuitEvent(
                agent_role=agent_role,
                change_id=change_id,
                severity="SEV-2",
                reason=f"circuit opened after {len(bucket)} rejects within {self.window_seconds}s",
            )
            if len(bucket) >= self.threshold
            else None
        )

    def is_open(self, agent_role: str, change_id: str) -> bool:
        key = (agent_role, change_id)
        bucket = self._rejects.get(key)
        if bucket is None:
            return False
        now = time.monotonic()
        self._prune(bucket, now)
        if not bucket:
            self._rejects.pop(key, None)
            return False
        return len(bucket) >= self.threshold

    def reset(self, agent_role: str, change_id: str) -> None:
        self._rejects.pop((agent_role, change_id), None)

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def _evict_if_needed(self) -> None:
        while len(self._rejects) > MAX_ACTIVE_KEYS:
            self._rejects.popitem(last=False)


class RateLimiter:
    def __init__(self, qps: int) -> None:
        if qps <= 0:
            raise ValueError("qps must be positive")
        self.qps = qps
        self._windows: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()

    def acquire(self, agent_role: str, model_id: str) -> bool:
        key = (agent_role, model_id)
        window = self._windows.get(key)
        if window is None:
            window = deque()
            self._windows[key] = window
        self._windows.move_to_end(key)
        now = time.monotonic()
        self._prune(window, now)
        if len(window) >= self.qps:
            self._evict_if_needed()
            return False
        window.append(now)
        self._evict_if_needed()
        return True

    def _prune(self, window: deque[float], now: float) -> None:
        cutoff = now - 1.0
        while window and window[0] < cutoff:
            window.popleft()

    def _evict_if_needed(self) -> None:
        while len(self._windows) > MAX_ACTIVE_KEYS:
            self._windows.popitem(last=False)
