"""Layer 3 — scenario data integrity over the live ClickHouse _audit_log.

Seeds the deterministic 15-scenario distribution (scripts/seed_scenarios.py), then
verifies, on the REAL backend: the rows land with the exact (status, tool, levels)
shapes A0's row-mappers key on; the hash chain is intact genesis->tip; no PHI sits
in any semantic column; the A0 traffic window filter narrows correctly (regression
for the naive/aware-datetime 500 fixed in _parse_timestamp); and an audit-export
appends a NEW chained row (the closed-loop write-back).

Skip-gated on MEDHARNESS_LIVE_BASE + a running stack.
"""

from __future__ import annotations

GENESIS = "0" * 64
# Columns whose values are hex hashes / UUIDs — excluded from the PHI scan (a 64-hex
# digest can incidentally contain a digit run; only SEMANTIC columns carry meaning).
_HASH_COLUMNS = {"event_id", "input_hash", "output_hash", "prev_hash", "current_hash"}

_AUDIT_COLUMNS = (
    "event_id, toString(timestamp) AS timestamp, actor_agent_role, actor_model_id, "
    "actor_vendor_family, action_tool, action_operation, context_data_levels, "
    "result_status, result_reason, prev_hash, current_hash, row_id"
)


def _rows(ch_query) -> list[dict]:
    return ch_query(f"SELECT {_AUDIT_COLUMNS} FROM _audit_log ORDER BY row_id ASC")


def test_seeded_distribution_matches_manifest(scenario_seed, ch_query):
    m = scenario_seed()
    rows = _rows(ch_query)
    assert len(rows) == m["total"], f"row count {len(rows)} != manifest {m['total']}"

    sec = sum(
        1
        for r in rows
        if r["result_status"] in ("blocked", "warn", "failed")
        or r["action_tool"] in ("prompt-injection-scan", "outbound-safety")
    )
    red = sum(1 for r in rows if r["result_status"] in ("blocked", "failed"))
    warn = sum(1 for r in rows if r["result_status"] == "warn")
    assert sec == m["sec_count"], f"sec rows {sec} != {m['sec_count']}"
    assert red == m["blocked_red_count"], f"red rows {red} != {m['blocked_red_count']}"
    assert warn == m["warn_count"], f"warn rows {warn} != {m['warn_count']}"
    # the seeder must emit A0's EXACT status strings (not warned/degraded)
    assert {r["result_status"] for r in rows} <= {"success", "blocked", "warn", "failed"}


def test_hash_chain_intact(scenario_seed, ch_query):
    scenario_seed()
    rows = _rows(ch_query)
    assert rows, "no audit rows after seeding"
    assert rows[0]["prev_hash"] == GENESIS, f"genesis prev_hash = {rows[0]['prev_hash']!r}"
    prev = GENESIS
    for i, r in enumerate(rows):
        assert int(r["row_id"]) == i + 1, f"row_id not monotonic at index {i}: {r['row_id']}"
        assert r["prev_hash"] == prev, f"chain break at row_id {r['row_id']}"
        prev = r["current_hash"]


def test_zero_phi_in_semantic_columns(scenario_seed, ch_query, no_phi):
    scenario_seed()
    rows = _rows(ch_query)
    for r in rows:
        semantic = " ".join(str(v) for k, v in r.items() if k not in _HASH_COLUMNS)
        no_phi(semantic, f"_audit_log row_id={r['row_id']}")


def test_traffic_window_filter_narrows(scenario_seed, http):
    # Regression for the _parse_timestamp naive/aware bug: windowed /traffic used to
    # 500. It must now 200 and narrow 7d >= 24h >= 1h, matching the seeded manifest.
    m = scenario_seed()
    wc = m["window_counts"]
    for window in ("1h", "24h", "7d"):
        r = http("GET", f"/api/v1/traffic?window={window}")
        assert r.status == 200, f"window={window}: {r.status} {r.text[:160]}"
        assert r.json()["inbound"]["gate"]["hit"] == wc[window] * 3, (
            f"window={window}: hit={r.json()['inbound']['gate']['hit']} want {wc[window] * 3}"
        )
    # no-window default sees every row
    r = http("GET", "/api/v1/traffic")
    assert r.json()["inbound"]["gate"]["hit"] == m["gate_default"]["hit"]


def test_audit_export_appends_chained_row(scenario_seed, ch_query, http):
    scenario_seed()
    before = ch_query("SELECT current_hash, row_id FROM _audit_log ORDER BY row_id DESC LIMIT 1")
    assert before, "no rows to export against"
    tip_hash, tip_id = before[0]["current_hash"], int(before[0]["row_id"])

    r = http("POST", "/api/v1/audit/export", body={})
    assert r.status == 200, f"export: {r.status} {r.text[:160]}"
    body = r.json()
    assert body.get("bundle_id") and body.get("sha256"), f"export missing fields: {body}"

    after = ch_query("SELECT prev_hash, row_id FROM _audit_log ORDER BY row_id DESC LIMIT 1")
    assert int(after[0]["row_id"]) == tip_id + 1, "export did not append exactly one row"
    assert after[0]["prev_hash"] == tip_hash, "export row did not chain onto the prior tip"
