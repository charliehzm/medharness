#!/usr/bin/env python3
"""
PreToolUse Hook · 模型路由 Gate
=================================
作用：拦截可能触发外部模型调用的 tool（WebFetch / Bash 中包含模型 API endpoint），
按当前 change 的 MODEL_ALLOWLIST.json 校验是否允许。

M1 占位行为：仅识别常见 LLM endpoint 关键字（api.openai.com / api.anthropic.com 等），
若 allowlist 不允许则警告（不阻断）。
M2 完整行为：调用 mcp-model-router 做 allowlist 比对，越权 → 阻断（exit 2）。
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

LLM_ENDPOINT_PATTERNS = {
    "openai-public": re.compile(r"api\.openai\.com"),
    "anthropic-public": re.compile(r"api\.anthropic\.com"),
    "openrouter": re.compile(r"openrouter\.ai"),
    "deepseek-public": re.compile(r"api\.deepseek\.com"),
    "qwen-public": re.compile(r"dashscope\.aliyuncs\.com"),
}


def find_active_change(project_dir: Path) -> Path | None:
    env_change = os.environ.get("CLAUDE_ACTIVE_CHANGE")
    if env_change:
        p = project_dir / "openspec" / "changes" / env_change
        return p if p.exists() else None
    base = project_dir / "openspec" / "changes"
    if not base.exists():
        return None
    candidates = [d for d in base.iterdir() if d.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def load_allowlist(change: Path) -> dict | None:
    al = change / "MODEL_ALLOWLIST.json"
    if not al.exists():
        return None
    try:
        return json.loads(al.read_text(encoding="utf-8"))
    except Exception:
        return None


def detect_llm_call(tool_name: str, tool_input: dict) -> list[str]:
    """返回命中的 endpoint key 列表。"""
    text = ""
    if tool_name == "WebFetch":
        text = tool_input.get("url", "")
    elif tool_name == "Bash":
        text = tool_input.get("command", "")
    elif tool_name and tool_name.startswith("mcp__"):
        text = json.dumps(tool_input, ensure_ascii=False)

    hits = []
    for key, pat in LLM_ENDPOINT_PATTERNS.items():
        if pat.search(text):
            hits.append(key)
    return hits


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    log_dir = project_dir / ".audit"
    log_dir.mkdir(exist_ok=True)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    hits = detect_llm_call(tool_name, tool_input)
    if not hits:
        return 0

    change = find_active_change(project_dir)
    allowlist = load_allowlist(change) if change else None

    denied = []
    if allowlist:
        denied_set = set(allowlist.get("denied_models", []) or [])
        for h in hits:
            if h in denied_set:
                denied.append(h)

    log_line = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "model_router_gate",
        "phase": "M1-placeholder",
        "tool_name": tool_name,
        "endpoints_hit": hits,
        "denied": denied,
        "change": str(change.relative_to(project_dir)) if change else None,
    }
    with open(log_dir / "hook_model_router_gate.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_line, ensure_ascii=False) + "\n")

    if denied:
        print(
            "[Model Router Warning · M1 占位] 检测到可能调用禁止的 LLM endpoint: "
            + ", ".join(denied)
            + "\nM2 起将硬阻断。请改走私有部署或经 mcp-model-router 路由。",
            file=sys.stderr,
        )
        # M1 放行；M2 改 return 2
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
