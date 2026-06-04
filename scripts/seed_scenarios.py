#!/usr/bin/env python3
"""Deterministic 15-scenario seeder for the _audit_log table (closed-loop UI/data tests).

This is the production-realistic successor to dev_seed_audit.py. Instead of a
round-robin smear it writes a HAND-AUTHORED, deterministic distribution that maps
each Console screen assertion to specific rows, and prints a JSON manifest so tests
read EXPECTED values instead of hard-coding them.

0-PHI: EVERY value here is SYNTHETIC. No real patient data, no provider keys, no
production sampling. The synthetic cn-id used by the relay gate tests
(110101199001011237) is DELIBERATELY ABSENT here — audit rows carry only hashes +
Chinese reason strings, never a raw identifier in any semantic column.

Correctness vs dev_seed_audit.py: A0's row mappers key on the EXACT strings
`success|blocked|warn|failed` (see mcp/a0-api/app.py `_row_cat`/`_row_status`),
NOT `warned`/`degraded`. `actor_vendor_family ∈ {openai,anthropic}` ⇒ dev ctx, else
prod. `action_tool ∈ {prompt-injection-scan,outbound-safety}` ⇒ sec category. This
seeder emits those exact strings so sec/red/yellow/prod assertions land.

Usage (inside the a0-api container, where CLICKHOUSE_* env points at clickhouse:8123):
  docker cp scripts/seed_scenarios.py medharness-a0-api:/tmp/seed_scenarios.py
  docker exec medharness-a0-api python /tmp/seed_scenarios.py --reset            # human summary
  docker exec medharness-a0-api python /tmp/seed_scenarios.py --reset --emit-manifest  # JSON only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

GENESIS = "0" * 64
NS = uuid.NAMESPACE_URL

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {db}._audit_log
(
    event_id UUID,
    timestamp DateTime64(3, 'UTC'),
    actor_agent_role LowCardinality(String),
    actor_model_id String,
    actor_vendor_family LowCardinality(String),
    actor_session_id String,
    action_tool String,
    action_skill Nullable(String),
    action_operation LowCardinality(String),
    context_change_id Nullable(String),
    context_step Nullable(UInt8),
    context_data_levels Array(LowCardinality(String)),
    result_status LowCardinality(String),
    result_reason Nullable(String),
    result_duration_ms Float32,
    input_hash FixedString(64),
    output_hash FixedString(64),
    prev_hash FixedString(64),
    current_hash FixedString(64),
    row_id UInt64,
    inserted_at DateTime64(3) DEFAULT now64()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, row_id)
TTL toDateTime(timestamp) + INTERVAL 7 YEAR
SETTINGS index_granularity = 8192
"""

# Time buckets (seconds before "now"). Wide margins from the window boundaries
# (1h/24h/7d) so the few-second drift between seed-time and request-time never
# flips a row across a boundary. A0 filters with datetime.now(UTC) - horizon.
BUCKETS = {
    "recent":  {"base": 120,            "step": 60},        # 2..~32 min  -> in 1h,24h,7d,default
    "mid":     {"base": 2 * 3600,       "step": 600},       # 2h..        -> in 24h,7d,default (NOT 1h)
    "old":     {"base": 2 * 86400,      "step": 12 * 3600}, # 2d..        -> in 7d,default (NOT 24h)
    "ancient": {"base": 8 * 86400,      "step": 86400},     # 8d..        -> default only (NOT 7d)
}

# (key, count, role, model, vendor, tool, op, status, levels, reason, bucket, change_id)
# Recent scenarios first (drive default + 1h-window views); then mid/old/ancient
# filler rows that exercise window narrowing (S12).
SCENARIOS = [
    ("S1",  8, "coder",        "qwen-max-2026",   "alibaba",   "model-router",         "route",   "success", ["L3"],       "脱敏后放行",          "recent",  "chg-prod-rag"),
    ("S2",  6, "data-steward", "deepseek-v3",     "deepseek",  "desensitize",          "encrypt", "success", ["L3"],       "脱敏后放行",          "recent",  "chg-dify"),
    ("S3",  3, "data-steward", "qwen-max-2026",   "alibaba",   "phi-detector",         "scan",    "success", ["L3", "L4"], "PHI 命中→脱敏",       "recent",  "chg-phi"),
    ("S4",  4, "system",       "dify-rag",        "deepseek",  "prompt-injection-scan","detect",  "blocked", ["L2"],       "命中注入→隔离",       "recent",  "chg-inj"),
    ("S5",  2, "system",       "gpt-4o",          "openai",    "outbound-safety",      "scan",    "blocked", ["L2"],       "出站 PHI 回流→拦截",  "recent",  "chg-outbound"),
    ("S6",  2, "reviewer",     "gpt-4o",          "openai",    "model-router",         "route",   "failed",  ["L2"],       "异构拒绝·同厂商",     "recent",  "chg-hetero"),
    ("S7",  4, "coder",        "qwen-vl-2026",    "alibaba",   "model-router",         "route",   "success", ["L2"],       "embeddings 批处理放行","recent", "chg-comfy"),
    ("S8",  2, "coder",        "claude-opus-4.7", "anthropic", "phi-detector",         "scan",    "warn",    ["L3"],       "开发期误贴→告警",     "recent",  "chg-claude-dev"),
    ("M1",  4, "coder",        "qwen-max-2026",   "alibaba",   "model-router",         "route",   "success", ["L2"],       "脱敏后放行",          "mid",     "chg-prod-rag"),
    ("O1",  3, "coder",        "deepseek-v3",     "deepseek",  "model-router",         "route",   "success", ["L1"],       "常规放行",            "old",     "chg-prod-rag"),
    ("A1",  2, "system",       "glm-4.6",         "zhipu",     "model-router",         "route",   "success", ["L1"],       "历史聚合",            "ancient", "chg-sys"),
]


def _hex64(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _exec(sql: str, body: bytes | None = None) -> bytes:
    host = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")
    port = os.environ.get("CLICKHOUSE_HTTP_PORT", "18123")
    user = os.environ.get("CLICKHOUSE_USER", "default")
    pw = os.environ.get("CLICKHOUSE_PASSWORD", "")
    url = f"http://{host}:{port}/?query=" + urllib.parse.quote(sql)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("X-ClickHouse-User", user)
    if pw:
        req.add_header("X-ClickHouse-Key", pw)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _is_sec(tool: str, status: str) -> bool:
    return status in {"blocked", "warn", "failed"} or tool in {"prompt-injection-scan", "outbound-safety"}


def _is_dev(vendor: str) -> bool:
    return vendor in {"openai", "anthropic"}


def _top_level(levels: list[str]) -> str:
    for lv in ("L4", "L3", "L2"):
        if lv in levels:
            return lv
    return "L2"


def build_rows(now: datetime) -> tuple[list[dict], dict]:
    """Return (rows, manifest). Deterministic given `now`."""
    rows: list[dict] = []
    bucket_idx: dict[str, int] = {k: 0 for k in BUCKETS}
    by_scenario: dict[str, list[int]] = {}
    prev = GENESIS
    i = 0
    for key, count, role, model, vendor, tool, op, status, levels, reason, bucket, change_id in SCENARIOS:
        by_scenario[key] = []
        for _ in range(count):
            i += 1
            row_id = i
            b = BUCKETS[bucket]
            offset_s = b["base"] + bucket_idx[bucket] * b["step"]
            bucket_idx[bucket] += 1
            ts_dt = now - timedelta(seconds=offset_s)
            ts = ts_dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts_dt.microsecond // 1000:03d}"
            ihash, ohash = _hex64(f"in-{row_id}"), _hex64(f"out-{row_id}")
            cur = _hex64(f"{row_id}|{model}|{tool}|{status}|{ts}|{ihash}|{ohash}|{prev}")
            rows.append({
                "event_id": str(uuid.uuid5(NS, f"seed|{row_id}")),
                "timestamp": ts,
                "actor_agent_role": role,
                "actor_model_id": model,
                "actor_vendor_family": vendor,
                "actor_session_id": f"sess-{key.lower()}",
                "action_tool": tool,
                "action_skill": None,
                "action_operation": op,
                "context_change_id": change_id,
                "context_step": row_id % 12,
                "context_data_levels": levels,
                "result_status": status,
                "result_reason": reason,
                "result_duration_ms": round(2.0 + (row_id % 17) * 1.3, 1),
                "input_hash": ihash,
                "output_hash": ohash,
                "prev_hash": prev,
                "current_hash": cur,
                "row_id": row_id,
                "_key": key,
                "_bucket": bucket,
                "_sec": _is_sec(tool, status),
                "_dev": _is_dev(vendor),
                "_level": _top_level(levels),
            })
            by_scenario[key].append(row_id)
            prev = cur

    # Derived manifest counts (over ALL rows — posture/events read without a window).
    sec = [r for r in rows if r["_sec"]]
    comp = [r for r in rows if not r["_sec"]]
    red = [r for r in rows if r["result_status"] in {"blocked", "failed"}]
    warn = [r for r in rows if r["result_status"] == "warn"]
    prod_models = sorted({r["actor_model_id"] for r in rows if not r["_dev"]})

    def win_count(seconds: int) -> int:
        # rows whose timestamp >= now - seconds (A0's window predicate)
        cutoff = now - timedelta(seconds=seconds)
        return sum(1 for r in rows
                   if datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc) >= cutoff)

    # A representative ref per probe (A0 _row_ref => 'routing#<current_hash[:4]>').
    def ref_of(row_id: int) -> str:
        ch = next(r["current_hash"] for r in rows if r["row_id"] == row_id)
        return f"routing#{ch[:4]}"

    tip = rows[-1]["current_hash"]
    manifest = {
        "total": len(rows),
        "comp_count": len(comp),
        "sec_count": len(sec),
        "blocked_red_count": len(red),
        "warn_count": len(warn),
        "prod_models": prod_models,
        "distinct_prod_upstreams": len(prod_models),
        "window_counts": {"1h": win_count(3600), "24h": win_count(86400), "7d": win_count(7 * 86400)},
        "by_scenario": by_scenario,
        "refs": {
            "phi_l4": ref_of(by_scenario["S3"][0]),       # Audit drill: L4 lineage
            "injection": ref_of(by_scenario["S4"][0]),    # sec event / 注入
            "tip_full": tip,                              # full current_hash of newest row
            "tip_routing": f"routing#{tip[:4]}",
        },
        "gate_default": {  # /traffic with NO window (Console default view)
            "hit": len(rows) * 3,
            "blocked": len(red) + len(warn),
            "passed": len(rows) * 10,
        },
    }
    return rows, manifest


def seed(reset: bool, emit_manifest: bool) -> None:
    db = os.environ.get("CLICKHOUSE_DATABASE", "medharness")
    _exec(f"CREATE DATABASE IF NOT EXISTS {db}")
    _exec(CREATE_TABLE.format(db=db))
    if reset:
        _exec(f"TRUNCATE TABLE IF EXISTS {db}._audit_log")

    now = datetime.now(timezone.utc)
    rows, manifest = build_rows(now)
    payload = "\n".join(
        json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False)
        for r in rows
    )
    _exec(f"INSERT INTO {db}._audit_log FORMAT JSONEachRow", body=payload.encode("utf-8"))
    count = int(_exec(f"SELECT count() FROM {db}._audit_log").decode().strip() or "0")
    manifest["table_count_after"] = count

    if emit_manifest:
        print(json.dumps(manifest, ensure_ascii=False))
    else:
        print(
            f"seeded {manifest['total']} scenario rows (comp={manifest['comp_count']} "
            f"sec={manifest['sec_count']} red={manifest['blocked_red_count']} warn={manifest['warn_count']}); "
            f"table now has {count}; window 1h/24h/7d="
            f"{manifest['window_counts']['1h']}/{manifest['window_counts']['24h']}/{manifest['window_counts']['7d']}; "
            f"tip={manifest['refs']['tip_routing']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="TRUNCATE before seeding")
    ap.add_argument("--emit-manifest", action="store_true", help="print ONLY the JSON manifest")
    args = ap.parse_args()
    try:
        seed(args.reset, args.emit_manifest)
    except Exception as exc:  # noqa: BLE001
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
