#!/usr/bin/env python3
"""
PreToolUse Hook v2 · 模型路由强阻断（M3 起用）
=================================================
与 v1 的差异：
- 调 mcp-model-router v2 的 route（带 phi 二次校验）
- HOOK_MODE=block 时拒绝放行
- 阻断事件落 audit-log
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
ROUTER_BIN = str(PROJECT_DIR / "mcp" / "model-router" / "server_v2.py")
AUDIT_LOG_BIN = str(PROJECT_DIR / "mcp" / "audit-log" / "server.py")
HOOK_MODE = os.environ.get("CLAUDE_HOOK_MODE", "warn")


LLM_PATTERNS = {
    "openai-public": re.compile(r"api\.openai\.com"),
    "anthropic-public": re.compile(r"api\.anthropic\.com"),
    "deepseek-public": re.compile(r"api\.deepseek\.com"),
    "qwen-public": re.compile(r"dashscope\.aliyuncs\.com"),
    "openrouter": re.compile(r"openrouter\.ai"),
}


def find_active_change() -> str | None:
    env_change = os.environ.get("CLAUDE_ACTIVE_CHANGE")
    if env_change:
        p = PROJECT_DIR / "openspec" / "changes" / env_change
        return env_change if p.exists() else None
    base = PROJECT_DIR / "openspec" / "changes"
    if not base.exists():
        return None
    candidates = [d for d in base.iterdir() if d.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime).name


def detect_llm(tool_name: str, tool_input: dict) -> list[str]:
    text = ""
    if tool_name == "WebFetch":
        text = tool_input.get("url", "")
    elif tool_name == "Bash":
        text = tool_input.get("command", "")
    elif tool_name and tool_name.startswith("mcp__"):
        text = json.dumps(tool_input, ensure_ascii=False)
    return [k for k, pat in LLM_PATTERNS.items() if pat.search(text)]


def call_router(change_id: str, task_type: str, prompt: str) -> dict:
    try:
        p = subprocess.run(
            ["python3", ROUTER_BIN, "route"],
            input=json.dumps(
                {
                    "change_id": change_id,
                    "task_type": task_type,
                    "prompt": prompt,
                },
                ensure_ascii=False,
            ),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if p.returncode != 0:
            return {"decision": "deny", "reason": "router_unavailable"}
        return json.loads(p.stdout)
    except Exception as e:
        return {"decision": "deny", "reason": f"router_error:{e}"}


def call_audit(event_type: str, payload: dict) -> None:
    try:
        subprocess.run(
            ["python3", AUDIT_LOG_BIN, "append"],
            input=json.dumps({"event_type": event_type, "payload": payload}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        pass


def main() -> int:
    log_dir = PROJECT_DIR / ".audit"
    log_dir.mkdir(exist_ok=True)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    hits = detect_llm(tool_name, tool_input)
    if not hits:
        return 0

    change_id = find_active_change()
    decision = {"decision": "deny", "reason": "no_change_no_allowlist"}
    if change_id:
        # 任务类型从环境变量或猜测
        task_type = os.environ.get("CLAUDE_TASK_TYPE", "coder")
        # 用 hits[0] 作为预期模型简代
        prompt_preview = json.dumps(tool_input, ensure_ascii=False)[:2000]
        decision = call_router(change_id, task_type, prompt_preview)

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "model_router_gate_v2",
        "mode": HOOK_MODE,
        "endpoints_hit": hits,
        "decision": decision,
    }
    with open(log_dir / "hook_model_router_gate.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if decision.get("decision") != "allow":
        call_audit("model_route_block", record)
        msg = {
            "decision": "block",
            "reason": decision.get("reason"),
            "next_action": "改走私有部署 / 经 mcp-model-router 走 allowlist 内模型。",
        }
        print(json.dumps(msg, ensure_ascii=False), file=sys.stderr)
        return 2 if HOOK_MODE == "block" else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
