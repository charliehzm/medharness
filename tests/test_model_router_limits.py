from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "model-router"))

from limits import MAX_ACTIVE_KEYS, CircuitBreaker, RateLimiter  # noqa: E402


def test_five_rejects_open_circuit() -> None:
    breaker = CircuitBreaker()
    for _ in range(4):
        assert breaker.record_reject("coder", "change-1") is None
        assert not breaker.is_open("coder", "change-1")
    event = breaker.record_reject("coder", "change-1")
    assert event is not None
    assert event.severity == "SEV-2"
    assert breaker.is_open("coder", "change-1")


def test_threshold_three_opens_on_third_reject() -> None:
    breaker = CircuitBreaker(threshold=3)
    assert breaker.record_reject("compliance", "change-2") is None
    assert breaker.record_reject("compliance", "change-2") is None
    event = breaker.record_reject("compliance", "change-2")
    assert event is not None
    assert breaker.is_open("compliance", "change-2")


def test_window_expires_clears_rejects() -> None:
    breaker = CircuitBreaker(threshold=2, window_seconds=1)
    breaker.record_reject("reviewer", "change-3")
    time.sleep(1.1)
    assert not breaker.is_open("reviewer", "change-3")
    assert breaker.record_reject("reviewer", "change-3") is None


def test_circuit_isolated_by_agent_and_change() -> None:
    breaker = CircuitBreaker(threshold=2)
    breaker.record_reject("coder", "change-1")
    breaker.record_reject("coder", "change-1")
    assert breaker.is_open("coder", "change-1")
    assert not breaker.is_open("coder", "change-2")
    assert not breaker.is_open("docs", "change-1")


def test_rate_limiter_denies_eleventh_call_in_same_second() -> None:
    limiter = RateLimiter(qps=10)
    for _ in range(10):
        assert limiter.acquire("coder", "qwen-max")
    assert not limiter.acquire("coder", "qwen-max")


def test_rate_limiter_isolated_by_agent_and_model() -> None:
    limiter = RateLimiter(qps=1)
    assert limiter.acquire("coder", "qwen-max")
    assert limiter.acquire("docs", "qwen-max")
    assert limiter.acquire("coder", "gpt-5")
    assert not limiter.acquire("coder", "qwen-max")


def test_lru_evicts_after_1000_active_keys() -> None:
    breaker = CircuitBreaker()
    for index in range(MAX_ACTIVE_KEYS + 25):
        breaker.record_reject(f"agent-{index}", f"change-{index}")
    assert len(breaker._rejects) <= MAX_ACTIVE_KEYS

    limiter = RateLimiter(qps=1)
    for index in range(MAX_ACTIVE_KEYS + 25):
        assert limiter.acquire(f"agent-{index}", f"model-{index}")
    assert len(limiter._windows) <= MAX_ACTIVE_KEYS


def test_performance_is_under_100us_per_call() -> None:
    breaker = CircuitBreaker()
    limiter = RateLimiter(qps=10)

    start = time.perf_counter_ns()
    for index in range(100_000):
        agent = f"agent-{index % 8}"
        change = f"change-{index % 8}"
        model = f"model-{index % 8}"
        breaker.record_reject(agent, change)
        breaker.is_open(agent, change)
        limiter.acquire(agent, model)
    elapsed_us = (time.perf_counter_ns() - start) // 1_000

    assert elapsed_us / (100_000 * 3) < 100
