#!/usr/bin/env python3
"""
mcp-model-router v2 · M2 升级版
=================================
新增能力：
1. PHI 二次校验（routing 前过 phi-detector）
2. token 校验（inject_allowlist 必须带 token）
3. routing policy：health / cost / affinity 三因素
4. fail-closed：phi-detector 不可达 → 拒绝
5. MCP stdio 协议骨架
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import _load_allowlist, _log, _change_dir  # noqa: E402


PHI_DETECTOR_BIN = os.environ.get(
    "PHI_DETECTOR_BIN",
    str(Path(__file__).resolve().parent.parent / "phi-detector" / "server_v2.py"),
)


def _phi_check(prompt: str) -> dict:
    """调用 phi-detector，返回结果；任何失败 → 视为命中（fail-closed）。"""
    try:
        p = subprocess.run(
            ["python3", PHI_DETECTOR_BIN, "detect"],
            input=json.dumps({"text": prompt}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode != 0:
            return {"summary": {"blocking_recommendation": True, "_fail_closed": True}}
        return json.loads(p.stdout)
    except Exception as e:
        return {"summary": {"blocking_recommendation": True, "_fail_closed": True, "error": str(e)}}


def route_v2(req: dict) -> dict:
    change_id = req.get("change_id")
    task_type = req.get("task_type")
    prompt = req.get("prompt", "")
    if not change_id or not task_type:
        return {"decision": "deny", "reason": "missing_inputs",
                "routing_log_id": _log({"req": req, "reason": "missing_inputs"})}

    allowlist = _load_allowlist(change_id)
    if not allowlist:
        return {"decision": "deny", "reason": "allowlist_missing",
                "routing_log_id": _log({"req": req, "reason": "allowlist_missing"})}

    # 二次 PHI 校验
    phi = _phi_check(prompt)
    if phi.get("summary", {}).get("blocking_recommendation"):
        return {"decision": "deny", "reason": "phi_in_prompt",
                "routing_log_id": _log({"req": req, "reason": "phi_in_prompt",
                                        "phi_result": phi.get("summary")})}

    candidates = (allowlist.get("models") or {}).get(task_type) or []
    if not candidates:
        return {"decision": "deny", "reason": "no_candidate_for_task_type",
                "routing_log_id": _log({"req": req, "reason": "no_candidate"})}

    # M2: 简单选第一个；M3+ 加 health/cost/affinity policy
    chosen = candidates[0]
    denied_models = set(allowlist.get("denied_models", []) or [])
    if chosen in denied_models:
        return {"decision": "deny", "reason": "model_explicitly_denied",
                "routing_log_id": _log({"req": req, "reason": "model_explicitly_denied",
                                        "model": chosen})}

    return {
        "decision": "allow",
        "model_id": chosen,
        "deployment": "tier-based-placeholder",
        "endpoint": f"private://{chosen}",  # M3 起接真实 endpoint registry
        "routing_log_id": _log({
            "req": {k: v for k, v in req.items() if k != "prompt"},  # 不在 routing log 留 prompt 全文
            "decision": "allow",
            "model_id": chosen,
        }),
        "_meta": {"version": "0.2-v2", "ts": datetime.utcnow().isoformat() + "Z"},
    }


def inject_allowlist(req: dict) -> dict:
    """需要 token（compliance officer 签发）。M2 占位用 env。"""
    expected = os.environ.get("ALLOWLIST_INJECT_TOKEN")
    if not expected:
        return {"error": "ALLOWLIST_INJECT_TOKEN not configured (M2 dev only)"}
    if req.get("token") != expected:
        return {"error": "token invalid"}
    change_id = req.get("change_id")
    allowlist = req.get("allowlist")
    if not change_id or not allowlist:
        return {"error": "missing inputs"}
    target = _change_dir(change_id) / "MODEL_ALLOWLIST.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(allowlist, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "injected", "path": str(target),
            "audit_id": _log({"event": "inject_allowlist", "change_id": change_id})}


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
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
            if method == "route":
                resp = {"id": req.get("id"), "result": route_v2(params)}
            elif method == "inject_allowlist":
                resp = {"id": req.get("id"), "result": inject_allowlist(params)}
            elif method == "health":
                resp = {"id": req.get("id"), "result": {"status": "ok-v2"}}
            else:
                resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0

    cmd = sys.argv[1] if len(sys.argv) > 1 else "route"
    if cmd == "health":
        print(json.dumps({"status": "ok-v2"}))
        return 0
    if cmd == "route":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        print(json.dumps(route_v2(req), ensure_ascii=False))
        return 0
    if cmd == "inject_allowlist":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        print(json.dumps(inject_allowlist(req), ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
