from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "audit-log"))

from hashchain import (  # noqa: E402
    GENESIS_PREV_HASH,
    canonical_json,
    compute_hash,
    verify_chain,
)


def _event(row_id: int, **overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": f"00000000-0000-4000-8000-{row_id:012d}",
        "timestamp": f"2026-05-24T03:{row_id % 60:02d}:00.000Z",
        "actor": {
            "agent_role": "coder",
            "model_id": "synthetic-model",
            "vendor_family": "synthetic",
            "session_id": f"synthetic-session-{row_id}",
        },
        "action": {
            "tool": "synthetic-tool",
            "skill": None,
            "operation": "write",
        },
        "context": {
            "change_id": "feat-edge-tier-production-v0.5.0",
            "step": 6,
            "data_levels": ["L1"],
        },
        "result": {
            "status": "success",
            "reason": None,
            "duration_ms": float(row_id),
        },
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
        "row_id": row_id,
    }
    event.update(overrides)
    return event


def _chain(size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prev_hash = GENESIS_PREV_HASH
    for row_id in range(size):
        event = _event(row_id)
        current_hash = compute_hash(event, prev_hash)
        rows.append({**event, "prev_hash": prev_hash, "current_hash": current_hash})
        prev_hash = current_hash
    return rows


def test_genesis_hash_is_constant() -> None:
    assert GENESIS_PREV_HASH == "GENESIS"
    rows = _chain(1)
    assert rows[0]["prev_hash"] == GENESIS_PREV_HASH


def test_compute_hash_deterministic() -> None:
    event = _event(1)
    hashes = {compute_hash(event, GENESIS_PREV_HASH) for _ in range(100)}

    assert len(hashes) == 1


def test_compute_hash_changes_with_event() -> None:
    event = _event(1)
    changed = _event(1, output_hash="c" * 64)

    assert compute_hash(event, GENESIS_PREV_HASH) != compute_hash(changed, GENESIS_PREV_HASH)


def test_compute_hash_changes_with_prev() -> None:
    event = _event(1)

    assert compute_hash(event, GENESIS_PREV_HASH) != compute_hash(event, "f" * 64)


def test_canonical_json_field_order_invariant() -> None:
    event_a = {"a": 1, "b": 2}
    event_b = {"b": 2, "a": 1}

    assert canonical_json(_event(1, actor=event_a)) == canonical_json(_event(1, actor=event_b))
    assert compute_hash(_event(1, actor=event_a), GENESIS_PREV_HASH) == compute_hash(
        _event(1, actor=event_b),
        GENESIS_PREV_HASH,
    )


def test_verify_chain_passes_for_100_rows() -> None:
    assert verify_chain(_chain(100)) == (True, None)


def test_verify_chain_detects_tamper_at_row_50() -> None:
    rows = _chain(100)
    tampered = copy.deepcopy(rows)
    tampered[50]["result"]["status"] = "error"

    assert verify_chain(tampered) == (False, 50)


def test_verify_chain_detects_missing_genesis() -> None:
    rows = _chain(3)
    rows[0]["prev_hash"] = "not-genesis"

    assert verify_chain(rows) == (False, 0)


def test_canonical_json_missing_required_field_fails_closed() -> None:
    event = _event(1)
    del event["row_id"]

    with pytest.raises(ValueError, match="row_id"):
        canonical_json(event)


def test_verify_chain_missing_required_field_fails_closed_at_row_id() -> None:
    rows = _chain(3)
    del rows[2]["output_hash"]

    assert verify_chain(rows) == (False, 2)
