#!/usr/bin/env python3
"""
mcp-model-router · M1 占位实现
================================
M2 完整实现要点：
- 接 phi-detector 做二次校验
- 接 allowlist injection（带 token）
- 路由决策与转发分离，转发可挂多 endpoint
- MCP server 协议封装

本占位提供 CLI 形态的 route / inject_allowlist / health 子命令。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _audit_dir() -> Path:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    d = project_dir / ".audit"
    d.mkdir(exist_ok=True)
    return d


def _change_dir(change_id: str) -> Path:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    return project_dir / "openspec" / "changes" / change_id


def _load_allowlist(change_id: str) -> dict | None:
    al = _change_dir(change_id) / "MODEL_ALLOWLIST.json"
    if not al.exists():
        return None
    try:
        return json.loads(al.read_text(encoding="utf-8"))
    except Exception:
        return None


def _log(record: dict) -> str:
    record_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + str(os.getpid())
    record["routing_log_id"] = record_id
    with open(_audit_dir() / "routing_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record_id


def route(req: dict) -> dict:
    change_id = req.get("change_id")
    task_type = req.get("task_type")
    if not change_id or not task_type:
        return {
            "decision": "deny",
            "reason": "missing_inputs",
            "routing_log_id": _log({"req": req, "reason": "missing_inputs"}),
        }

    allowlist = _load_allowlist(change_id)
    if not allowlist:
        return {
            "decision": "deny",
            "reason": "allowlist_missing",
            "routing_log_id": _log({"req": req, "reason": "allowlist_missing"}),
        }

    candidates = (allowlist.get("models") or {}).get(task_type) or []
    if not candidates:
        return {
            "decision": "deny",
            "reason": "no_candidate_for_task_type",
            "routing_log_id": _log({"req": req, "reason": "no_candidate"}),
        }

    # M1: 不做 phi-detector 二次校验（M2 加上）
    chosen = candidates[0]
    return {
        "decision": "allow",
        "model_id": chosen,
        "deployment": "placeholder",
        "endpoint": "stub://placeholder",
        "routing_log_id": _log({"req": req, "decision": "allow", "model_id": chosen}),
        "_meta": {"version": "0.1-placeholder", "ts": datetime.utcnow().isoformat() + "Z"},
    }


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "route"

    if cmd == "health":
        print(json.dumps({"status": "ok-placeholder"}))
        return 0

    if cmd == "route":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        print(json.dumps(route(req), ensure_ascii=False))
        return 0

    if cmd == "inject_allowlist":
        # M1: 占位 —— allowlist 实际由开发者直接放到 change 目录下
        print(
            json.dumps(
                {
                    "status": "noop-placeholder",
                    "note": "M1 由 compliance-precheck Skill 直接写入 change 目录。M2 起本端点强制 token 校验。",
                }
            )
        )
        return 0

    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
