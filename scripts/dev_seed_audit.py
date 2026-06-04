#!/usr/bin/env python3
"""Dev-only synthetic seeder for the _audit_log table (INT-5 local 连调).

0-PHI: EVERY value here is SYNTHETIC. No real patient data, no real provider
keys, no production sampling. Exists only to exercise A0's live ClickHouse path
locally so the Console can be driven against a real query backend.

Usage:
  CLICKHOUSE_HOST=127.0.0.1 CLICKHOUSE_HTTP_PORT=18123 \\
    python scripts/dev_seed_audit.py [--rows N] [--reset]
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

# Synthetic dimensions (all fake).
ROLES = ["coder", "compliance", "reviewer", "pm", "data-steward", "system"]
MODELS = ["qwen-max-2026", "claude-opus-4.7", "gpt-4o", "dify-rag", "deepseek-v3", "glm-4.6"]
VENDORS = {
    "qwen-max-2026": "alibaba",
    "claude-opus-4.7": "anthropic",
    "gpt-4o": "openai",
    "dify-rag": "openai",
    "deepseek-v3": "deepseek",
    "glm-4.6": "zhipu",
}
TOOLS = [
    "model-router",
    "phi-detector",
    "desensitize",
    "prompt-injection-scan",
    "outbound-safety",
    "audit-export",
]
OPS = {
    "model-router": "route",
    "phi-detector": "scan",
    "desensitize": "encrypt",
    "prompt-injection-scan": "detect",
    "outbound-safety": "scan",
    "audit-export": "export",
}
STATUSES = ["success", "success", "success", "blocked", "warned", "degraded"]
LEVELS = [["L1"], ["L2"], ["L3"], ["L3", "L4"], ["L2", "L3"]]
REASONS = {
    "success": "脱敏后放行",
    "blocked": "命中红线→拒绝",
    "warned": "低置信→告警",
    "degraded": "降级路由",
}


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


def seed(rows: int, reset: bool) -> None:
    db = os.environ.get("CLICKHOUSE_DATABASE", "medharness")
    _exec(f"CREATE DATABASE IF NOT EXISTS {db}")
    _exec(CREATE_TABLE.format(db=db))
    if reset:
        _exec(f"TRUNCATE TABLE IF EXISTS {db}._audit_log")

    base = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
    prev = GENESIS
    lines: list[str] = []
    for i in range(rows):
        model = MODELS[i % len(MODELS)]
        tool = TOOLS[i % len(TOOLS)]
        status = STATUSES[i % len(STATUSES)]
        ts = (base + timedelta(minutes=7 * i)).strftime("%Y-%m-%d %H:%M:%S.000")
        ihash, ohash = _hex64(f"in-{i}"), _hex64(f"out-{i}")
        cur = _hex64(f"{i}|{model}|{tool}|{status}|{ts}|{ihash}|{ohash}|{prev}")
        lines.append(
            json.dumps(
                {
                    "event_id": str(uuid.uuid4()),
                    "timestamp": ts,
                    "actor_agent_role": ROLES[i % len(ROLES)],
                    "actor_model_id": model,
                    "actor_vendor_family": VENDORS[model],
                    "actor_session_id": f"session-{i % 5}",
                    "action_tool": tool,
                    "action_skill": None,
                    "action_operation": OPS[tool],
                    "context_change_id": f"change-{i % 3}",
                    "context_step": i % 12,
                    "context_data_levels": LEVELS[i % len(LEVELS)],
                    "result_status": status,
                    "result_reason": REASONS.get(status, "ok"),
                    "result_duration_ms": round(2.0 + (i % 17) * 1.3, 1),
                    "input_hash": ihash,
                    "output_hash": ohash,
                    "prev_hash": prev,
                    "current_hash": cur,
                    "row_id": i + 1,
                },
                ensure_ascii=False,
            )
        )
        prev = cur

    _exec(f"INSERT INTO {db}._audit_log FORMAT JSONEachRow", body="\n".join(lines).encode("utf-8"))
    count = _exec(f"SELECT count() FROM {db}._audit_log").decode().strip()
    # Print the newest current_hash so callers can probe /api/v1/audit/<ref>.
    newest = (
        _exec(f"SELECT current_hash FROM {db}._audit_log ORDER BY row_id DESC LIMIT 1")
        .decode()
        .strip()
    )
    print(f"seeded {rows} synthetic rows; table now has {count}; newest current_hash={newest}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    try:
        seed(args.rows, args.reset)
    except Exception as exc:  # noqa: BLE001
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
