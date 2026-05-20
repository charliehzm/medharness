#!/usr/bin/env python3
"""
UserPromptSubmit Hook · PHI 检测兜底
=====================================
作用：在 prompt 提交给模型之前，扫描是否包含 PHI / PII。命中即非零退出码 + stderr JSON 阻断。

M1 占位行为：仅本地正则规则层，无 MCP 调用，命中只警告不阻断（exit 0）。
M2 完整行为：调用 mcp-phi-detector（规则 + 分类器双 pass），命中阻断（exit 2 + stderr JSON）。

Claude Code Hook 协议参考：
  https://docs.claude.com/en/docs/claude-code/hooks
约定：
  - stdin 收到 hook payload（JSON）
  - exit 0 = 放行
  - exit 2 = 阻断（stderr 内容作为 user-facing 拒绝原因）
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# ====== M1 占位规则层 ======
PHI_RULES = [
    ("CN-ID", re.compile(r"\b\d{17}[\dXx]\b")),
    ("CN-Phone", re.compile(r"\b1[3-9]\d{9}\b")),
    ("CN-Bank", re.compile(r"\b\d{16,19}\b")),
    ("Email", re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("Date-with-name", re.compile(r"\b\d{4}[-/年]\d{1,2}[-/月]\d{1,2}\b")),
]


def detect(text: str) -> list[dict]:
    hits = []
    for name, pat in PHI_RULES:
        for m in pat.finditer(text or ""):
            hits.append({"rule": name, "match": m.group()[:6] + "***", "span": [m.start(), m.end()]})
    return hits


def main() -> int:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    log_dir = Path(project_dir) / ".audit"
    log_dir.mkdir(exist_ok=True)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    prompt = payload.get("prompt") or payload.get("user_input") or ""
    hits = detect(prompt)

    log_line = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "phi_detect",
        "phase": "M1-placeholder",
        "prompt_len": len(prompt),
        "hits": hits,
    }
    with open(log_dir / "hook_phi_detect.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_line, ensure_ascii=False) + "\n")

    if hits:
        # M1: 仅警告
        msg = (
            "[PHI Warning · M1 占位] 检测到 {n} 处疑似 PHI/PII。"
            "M2 起将硬阻断。请考虑先经 phi-desensitize Skill 处理。\n"
            "命中规则: {rules}"
        ).format(n=len(hits), rules=", ".join(sorted({h["rule"] for h in hits})))
        print(msg, file=sys.stderr)
        # M1: exit 0 (放行 + 警告) ; M2: 改为 exit 2 (阻断)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
