#!/usr/bin/env python3
"""
mcp-pm-bridge · community-edition 实现（本地内存工单库 + JSONL 审计）
====================================================================
社区版定位：**单机 / 内存 / 0 外部依赖**（不接 Jira / 飞书 SDK）。

  - 工单进程内 dict 存储，重启即清空（社区版 demo 行为）；
  - 仍保留既有 JSONL 审计留痕（.audit/pm_bridge.jsonl，append-only）；
  - 时间戳一律 datetime.now(timezone.utc)（禁用裸 utcnow）；id 用 uuid。

接口契约：
  - create_compliance_ticket({title, description?, severity?, change_id?}) -> ticket
  - get_ticket({ticket_id})                                               -> ticket | error
  - list_tickets({status?})                                               -> {tickets, count}
  - update_ticket_status({ticket_id, status})                             -> ticket | error
  - notify({...})                                                         -> 审计记录 (+可挂工单备注)
  - sync_change({...})                                                    -> {synced, change_id, ...}
  - health()                                                              -> {status:"ok", tickets}

企业版（非社区）才接真实 Jira / 飞书；本文件不依赖之。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

VALID_STATUS = ("open", "in_progress", "resolved")
VALID_SEVERITY = ("low", "medium", "high", "critical")

# In-memory ticket store: {ticket_id: ticket_dict}
_TICKETS: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit_dir() -> Path:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    d = project_dir / ".audit"
    d.mkdir(exist_ok=True)
    return d


def _record(event: str, payload: dict) -> dict:
    rec = {
        "id": str(uuid.uuid4()),
        "ts": _now(),
        "event": event,
        "payload": payload,
    }
    with open(_audit_dir() / "pm_bridge.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _mint_ticket_id() -> str:
    return "PM-" + uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# 工单
# ---------------------------------------------------------------------------
def create_compliance_ticket(req: dict) -> dict:
    title = req.get("title")
    if not title or not str(title).strip():
        return {"created": False, "error": "missing title"}
    severity = req.get("severity") or "medium"
    if severity not in VALID_SEVERITY:
        severity = "medium"
    ticket_id = _mint_ticket_id()
    ticket = {
        "id": ticket_id,
        "title": title,
        "description": req.get("description", ""),
        "severity": severity,
        "status": "open",
        "created_at": _now(),
        "change_id": req.get("change_id"),
    }
    _TICKETS[ticket_id] = ticket
    _record("create_compliance_ticket", {"ticket_id": ticket_id, "input": req})
    return dict(ticket)


def get_ticket(req: dict) -> dict:
    ticket_id = req.get("ticket_id")
    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        return {"found": False, "ticket_id": ticket_id, "error": "not found"}
    return dict(ticket)


def list_tickets(req: dict) -> dict:
    status = req.get("status")
    tickets = list(_TICKETS.values())
    if status:
        tickets = [t for t in tickets if t.get("status") == status]
    # 稳定排序：按 created_at（同刻则按 id），新工单在前
    tickets.sort(key=lambda t: (t.get("created_at", ""), t.get("id", "")), reverse=True)
    return {"tickets": [dict(t) for t in tickets], "count": len(tickets)}


def update_ticket_status(req: dict) -> dict:
    ticket_id = req.get("ticket_id")
    status = req.get("status")
    if status not in VALID_STATUS:
        return {
            "updated": False,
            "ticket_id": ticket_id,
            "error": f"invalid status (expected one of {list(VALID_STATUS)})",
        }
    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        return {"updated": False, "ticket_id": ticket_id, "error": "not found"}
    prev = ticket.get("status")
    ticket["status"] = status
    ticket["updated_at"] = _now()
    _record(
        "update_ticket_status",
        {"ticket_id": ticket_id, "from": prev, "to": status},
    )
    return dict(ticket)


# ---------------------------------------------------------------------------
# 通知 / 变更同步
# ---------------------------------------------------------------------------
def notify(req: dict) -> dict:
    rec = _record("notify", req)
    out = {"notified": True, "audit_id": rec["id"], "ts": rec["ts"]}
    # 若引用了已知工单，挂一条备注
    ticket_id = req.get("ticket_id")
    if ticket_id and ticket_id in _TICKETS:
        ticket = _TICKETS[ticket_id]
        note = {"ts": rec["ts"], "message": req.get("message", "")}
        ticket.setdefault("notes", []).append(note)
        out["ticket_id"] = ticket_id
        out["note_count"] = len(ticket["notes"])
    return out


def sync_change(req: dict) -> dict:
    rec = _record("sync_change", req)
    return {
        "synced": True,
        "change_id": req.get("change_id"),
        "audit_id": rec["id"],
        "ts": rec["ts"],
    }


def health() -> dict:
    return {"status": "ok", "tickets": len(_TICKETS)}


# ---------------------------------------------------------------------------
# serve 模式
# ---------------------------------------------------------------------------
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
            elif method == "get_ticket":
                result = get_ticket(params)
            elif method == "list_tickets":
                result = list_tickets(params)
            elif method == "update_ticket_status":
                result = update_ticket_status(params)
            elif method == "notify":
                result = notify(params)
            elif method == "health":
                result = health()
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
    """Long-lived HTTP health endpoint so this service stays up in a detached
    container — the default `serve --stdio` hits stdin EOF and exits, which
    restart-loops under compose. Only GET /health is served (compose healthcheck)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path.rstrip("/") in ("", "/health"):
                payload = {"service": "pm-bridge", **health()}
                body = json.dumps(payload).encode("utf-8")
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
        print(json.dumps(health()))
        return 0
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    dispatch = {
        "sync_change": sync_change,
        "create_compliance_ticket": create_compliance_ticket,
        "get_ticket": get_ticket,
        "list_tickets": list_tickets,
        "update_ticket_status": update_ticket_status,
        "notify": notify,
    }
    if cmd in dispatch:
        print(json.dumps(dispatch[cmd](req), ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
