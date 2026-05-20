#!/usr/bin/env python3
"""mcp-pm-bridge · M5 占位实现（落到本地 jsonl；M5 起接 Jira/飞书 SDK）。"""
from __future__ import annotations
import json, os, sys, uuid
from datetime import datetime
from pathlib import Path


def _audit_dir() -> Path:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    d = project_dir / ".audit"
    d.mkdir(exist_ok=True)
    return d


def _record(event: str, payload: dict) -> dict:
    rec = {"id": str(uuid.uuid4()), "ts": datetime.utcnow().isoformat() + "Z",
           "event": event, "payload": payload}
    with open(_audit_dir() / "pm_bridge.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def sync_change(req: dict) -> dict:
    return _record("sync_change", req) | {"_note": "M5 占位"}


def create_compliance_ticket(req: dict) -> dict:
    return _record("create_compliance_ticket", req) | {"ticket_id": "PMSTUB-" + str(uuid.uuid4())[:8]}


def notify(req: dict) -> dict:
    return _record("notify", req) | {"_note": "M5 占位"}


def _serve_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: req = json.loads(line)
        except Exception: continue
        method = req.get("method"); params = req.get("params", {})
        try:
            if method == "sync_change": result = sync_change(params)
            elif method == "create_compliance_ticket": result = create_compliance_ticket(params)
            elif method == "notify": result = notify(params)
            elif method == "health": result = {"status": "ok-placeholder"}
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
        print(json.dumps({"status": "ok-placeholder"})); return 0
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if cmd == "sync_change":
        print(json.dumps(sync_change(req), ensure_ascii=False)); return 0
    if cmd == "create_compliance_ticket":
        print(json.dumps(create_compliance_ticket(req), ensure_ascii=False)); return 0
    if cmd == "notify":
        print(json.dumps(notify(req), ensure_ascii=False)); return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
