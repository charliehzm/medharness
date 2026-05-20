#!/usr/bin/env python3
"""
mcp-ci-trigger · M4 占位实现
==============================
本地实现：把 flag 写本地文件（.audit/flags.json），把 pipeline 调用记录到审计。
M4 真实接入：替换 _execute_pipeline / _set_flag_backend 即可。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path


def _project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _flags_path() -> Path:
    p = _project_root() / ".audit" / "flags.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_flags() -> dict:
    p = _flags_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _save_flags(flags: dict) -> None:
    _flags_path().write_text(json.dumps(flags, ensure_ascii=False, indent=2), encoding="utf-8")


def _audit(event_type: str, payload: dict) -> str:
    audit_id = str(uuid.uuid4())
    p = _project_root() / ".audit" / "ci_trigger.jsonl"
    rec = {"ts": datetime.utcnow().isoformat() + "Z", "id": audit_id,
           "event_type": event_type, "payload": payload}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return audit_id


def set_flag(req: dict) -> dict:
    flag = req["flag"]
    env = req.get("env", "dev")
    flags = _load_flags()
    key = f"{flag}::{env}"
    prev = flags.get(key, False)
    flags[key] = bool(req.get("value", False))
    _save_flags(flags)
    audit_id = _audit("set_flag", {"flag": flag, "env": env, "prev": prev,
                                   "new": flags[key], "change_id": req.get("change_id"),
                                   "actor": req.get("actor")})
    return {"prev_value": prev, "new_value": flags[key], "audit_id": audit_id}


def trigger_pipeline(req: dict) -> dict:
    pipeline = req["pipeline"]
    args = req.get("args", {})
    run_id = str(uuid.uuid4())
    # M4 占位：仅记录调用；M4 起调真实 CI
    audit_id = _audit("trigger_pipeline", {"pipeline": pipeline, "args": args, "run_id": run_id,
                                           "actor": req.get("actor")})
    return {"run_id": run_id, "audit_id": audit_id,
            "status_url": f"local://ci/{run_id}",
            "_note": "M4 占位 — 未实际执行 CI；M4 起接入 GitHub Actions"}


def rollback_stage(req: dict) -> dict:
    change_id = req["change_id"]
    stage = req["stage"]
    flag = f"stage{stage}_*"
    flags = _load_flags()
    # 把所有 stageN_* 的 canary/full 降回 staging
    changes = {}
    for k in list(flags.keys()):
        if k.startswith(f"stage{stage}_") and ("::canary" in k or "::full" in k):
            changes[k] = flags[k]
            flags[k] = False
    _save_flags(flags)
    audit_id = _audit("rollback_stage", {"change_id": change_id, "stage": stage,
                                         "flags_cleared": list(changes.keys()),
                                         "reason": req.get("reason")})
    return {"rolled_back_flags": list(changes.keys()), "audit_id": audit_id}


def _serve_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method")
        params = req.get("params", {})
        try:
            if method == "set_flag":
                result = set_flag(params)
            elif method == "trigger_pipeline":
                result = trigger_pipeline(params)
            elif method == "rollback_stage":
                result = rollback_stage(params)
            elif method == "list_flags":
                result = {"flags": _load_flags()}
            elif method == "health":
                result = {"status": "ok-placeholder", "flag_count": len(_load_flags())}
            else:
                resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n"); sys.stdout.flush(); continue
            resp = {"id": req.get("id"), "result": result}
        except Exception as e:
            resp = {"id": req.get("id"), "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":
        print(json.dumps({"status": "ok-placeholder", "flag_count": len(_load_flags())}))
        return 0
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if cmd == "set_flag":
        print(json.dumps(set_flag(req), ensure_ascii=False)); return 0
    if cmd == "trigger_pipeline":
        print(json.dumps(trigger_pipeline(req), ensure_ascii=False)); return 0
    if cmd == "rollback_stage":
        print(json.dumps(rollback_stage(req), ensure_ascii=False)); return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
