"""Layer 3 — data-integrity over the LIVE ClickHouse.

Verifies the audit hash-chain is intact end-to-end, the audit rows leak no PHI,
and the WORM schemas exist with the expected immutable columns/retention. Queries
run against the internal-only ClickHouse via the a0 container (ch_query fixture).
Requires seeded rows (scripts/dev_seed_audit.py) — skips cleanly if empty.
"""

from __future__ import annotations

import json

import pytest

GENESIS = "0" * 64


def test_audit_schema_exists(ch_query) -> None:
    rows = ch_query(
        "SELECT name FROM system.tables WHERE database='medharness' AND name='_audit_log'"
    )
    assert any(r["name"] == "_audit_log" for r in rows), (
        "WORM audit schema missing on the live stack"
    )


def test_audit_hash_columns_and_retention(ch_query) -> None:
    cols = ch_query(
        "SELECT name, type FROM system.columns WHERE database='medharness' AND table='_audit_log'"
    )
    by_name = {c["name"]: c["type"] for c in cols}
    assert by_name.get("prev_hash") == "FixedString(64)"
    assert by_name.get("current_hash") == "FixedString(64)"
    # 7-year retention TTL (HIPAA) declared on the table
    meta = ch_query(
        "SELECT engine_full FROM system.tables WHERE database='medharness' AND name='_audit_log'"
    )
    assert meta and "7" in meta[0]["engine_full"] and "TTL" in meta[0]["engine_full"]


def test_audit_hash_chain_is_intact(ch_query) -> None:
    rows = ch_query("SELECT row_id, prev_hash, current_hash FROM _audit_log ORDER BY row_id ASC")
    if not rows:
        pytest.skip("no seeded _audit_log rows (run scripts/dev_seed_audit.py)")
    assert rows[0]["prev_hash"] == GENESIS, f"genesis prev_hash != GENESIS: {rows[0]['prev_hash']}"
    prev: str | None = None
    for row in rows:
        if prev is not None:
            assert row["prev_hash"] == prev, f"hash chain broken at row_id={row['row_id']}"
        prev = row["current_hash"]
    ids = [int(r["row_id"]) for r in rows]  # CH returns UInt64 as a JSON string
    assert ids == sorted(ids), "row_id not monotonically increasing"
    assert len(set(ids)) == len(ids), "duplicate row_id in the chain"


def test_audit_rows_leak_no_phi(ch_query, no_phi) -> None:
    # Scan only the SEMANTIC columns: the hex hash/UUID columns would false-trigger
    # the phone/email regexes (a 64-hex digest can embed an 11-digit run).
    rows = ch_query(
        "SELECT actor_agent_role, actor_model_id, actor_vendor_family, actor_session_id, "
        "action_tool, action_skill, action_operation, context_change_id, "
        "result_status, result_reason FROM _audit_log ORDER BY row_id DESC LIMIT 100"
    )
    if not rows:
        pytest.skip("no seeded _audit_log rows")
    no_phi(json.dumps(rows, ensure_ascii=False), "live _audit_log semantic columns")
