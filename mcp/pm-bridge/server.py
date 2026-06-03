#!/usr/bin/env python3
"""mcp-pm-bridge · M5 占位实现（落到本地 jsonl；M5 起接 Jira/飞书 SDK）。"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path


def _audit_dir() -> Path:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    d = project_dir / ".audit"
    d.mkdir(exist_ok=True)
    return d


def _record(event: str, payload: dict) -> dict:
    rec = {
        "id": str(uuid.uuid4()),
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": event,
        "payload": payload,
    }
    with open(_audit_dir() / "pm_bridge.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def sync_change(req: dict) -> dict:
    return _record("sync_change", req) | {"_note": "M5 占位"}


def create_compliance_ticket(req: dict) -> dict:
    return _record("create_compliance_ticket", req) | {
        "ticket_id": "PMSTUB-" + str(uuid.uuid4())[:8]
    }


def notify(req: dict) -> dict:
    return _record("notify", req) | {"_note": "M5 占位"}


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
            if method == "sync_change":
                result = sync_change(params)
            elif method == "create_compliance_ticket":
                result = create_compliance_ticket(params)
            elif method == "notify":
                result = notify(params)
            elif method == "health":
                result = {"status": "ok-placeholder"}
            else:
                resp = {
                    "id": req.get("id"),
                    "error": {"code": -32601, "message": "Method not found"},
                }
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                continue
            resp = {"id": req.get("id"), "result": result}
        except Exception as e:
            resp = {"id": req.get("id"), "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def _serve_http(host: str, port: int) -> int:
    """Long-lived HTTP health endpoint so this v0.5.0-edge placeholder stays up in
    a detached container — the default `serve --stdio` hits stdin EOF and exits,
    which restart-loops under compose. Real behavior lands in a later milestone;
    for now only GET /health is served."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path.rstrip("/") in ("", "/health"):
                body = json.dumps({"status": "ok", "service": "pm-bridge", "stub": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    ThreadingHTTPServer((host, port), _Handler).serve_forever()
    return 0


def main() -> int:
    if sys.argv[1:3] == ["serve", "--http"]:
        host, port = "0.0.0.0", 9000
        rest = sys.argv[3:]
        for i, a in enumerate(rest):
            if a == "--host" and i + 1 < len(rest):
                host = rest[i + 1]
            elif a == "--port" and i + 1 < len(rest):
                port = int(rest[i + 1])
        return _serve_http(host, port)
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":
        print(json.dumps({"status": "ok-placeholder"}))
        return 0
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if cmd == "sync_change":
        print(json.dumps(sync_change(req), ensure_ascii=False))
        return 0
    if cmd == "create_compliance_ticket":
        print(json.dumps(create_compliance_ticket(req), ensure_ascii=False))
        return 0
    if cmd == "notify":
        print(json.dumps(notify(req), ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
