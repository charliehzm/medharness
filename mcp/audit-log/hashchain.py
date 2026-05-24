from __future__ import annotations

import hashlib
import json
from typing import Any, TypedDict

GENESIS_PREV_HASH = "GENESIS"
LEGACY_ZERO_PREV_HASH = "0" * 64

_REQUIRED_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "timestamp",
        "actor",
        "action",
        "context",
        "result",
        "input_hash",
        "output_hash",
        "row_id",
    }
)
_CHAIN_FIELDS = frozenset({"prev_hash", "current_hash"})


class AuditEvent(TypedDict):
    event_id: str
    timestamp: str
    actor: dict[str, Any]
    action: dict[str, Any]
    context: dict[str, Any]
    result: dict[str, Any]
    input_hash: str
    output_hash: str
    row_id: int


def _missing_required_fields(event: dict[str, Any]) -> list[str]:
    return sorted(field for field in _REQUIRED_EVENT_FIELDS if field not in event)


def _event_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in _CHAIN_FIELDS}


def _row_id(row: dict[str, Any], fallback_index: int) -> int:
    raw_row_id = row.get("row_id")
    if isinstance(raw_row_id, int):
        return raw_row_id
    return fallback_index


def canonical_json(event: dict[str, Any]) -> str:
    """Return deterministic compact JSON for an audit event.

    The event must include the T4 audit payload fields plus writer-assigned
    ``row_id``. Chain metadata is intentionally outside this canonical payload.
    """

    missing = _missing_required_fields(event)
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"audit event missing required field(s): {joined}")
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_hash(event: dict[str, Any], prev_hash: str) -> str:
    """Return sha256(canonical_json(event_with_row_id) + "|" + prev_hash)."""

    if not isinstance(prev_hash, str) or not prev_hash:
        raise ValueError("prev_hash must be a non-empty string")
    canonical = canonical_json(event)
    return hashlib.sha256(f"{canonical}|{prev_hash}".encode()).hexdigest()


def verify_chain(rows: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Verify a hash chain from GENESIS to tail.

    Returns ``(True, None)`` when every row links correctly. On failure it
    returns ``(False, broken_at_row_id)``. For a broken first-row genesis marker,
    the row id is normalized to ``0`` so callers can distinguish chain-head
    failures from an ordinary row hash mismatch.
    """

    expected_prev = GENESIS_PREV_HASH
    for index, row in enumerate(rows):
        row_id = _row_id(row, index)
        prev_hash = row.get("prev_hash")
        if index == 0 and prev_hash == LEGACY_ZERO_PREV_HASH:
            expected_prev = LEGACY_ZERO_PREV_HASH
        if prev_hash != expected_prev:
            if index == 0:
                return False, 0
            return False, row_id

        event = _event_payload(row)
        try:
            expected_current = compute_hash(event, prev_hash)
        except ValueError:
            return False, row_id
        if row.get("current_hash") != expected_current:
            return False, row_id
        expected_prev = expected_current

    return True, None
