#!/usr/bin/env python3
"""
mcp-phi-detector · M1 占位实现
================================
M2 完整实现要点（待开发）：
- 双 pass：规则 + 分类器（Qwen-1.8B / BERT）
- MCP server 协议（stdio / sse），符合 anthropic-mcp 规范
- 审计落盘 + 健康检查

本占位仅实现 `detect` 的 CLI 形态，供 Hook 与 CI 直接调用。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path


RULES = [
    ("CN-ID",      re.compile(r"\b\d{17}[\dXx]\b"),    0.95, "desensitize"),
    ("CN-Phone",   re.compile(r"\b1[3-9]\d{9}\b"),     0.95, "desensitize"),
    ("CN-Bank",    re.compile(r"\b\d{16,19}\b"),       0.7,  "review"),
    ("Email",      re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), 0.9, "desensitize"),
    ("Date-ISO",   re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),     0.6,  "review"),
    ("Date-CJK",   re.compile(r"\b\d{4}年\d{1,2}月\d{1,2}日?\b"),       0.6,  "review"),
]


def detect(text: str, context: dict | None = None) -> dict:
    hits = []
    max_conf = 0.0
    for name, pat, conf, action in RULES:
        for m in pat.finditer(text or ""):
            hits.append({
                "type": name,
                "span": [m.start(), m.end()],
                "confidence": conf,
                "suggested": action,
            })
            if conf > max_conf:
                max_conf = conf

    return {
        "hits": hits,
        "summary": {
            "total_hits": len(hits),
            "max_confidence": max_conf,
            "blocking_recommendation": max_conf >= 0.9,
        },
        "_meta": {
            "version": "0.1-placeholder",
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "passes": ["rule"],   # M2 会加 "classifier"
        },
    }


def main() -> int:
    """
    用法：
      echo '{"text":"..."}' | python server.py detect
      python server.py health
    """
    cmd = sys.argv[1] if len(sys.argv) > 1 else "detect"

    if cmd == "health":
        print(json.dumps({
            "status": "ok-placeholder",
            "rules_version": "0.1",
            "classifier": "not-loaded (M1)",
        }))
        return 0

    if cmd == "detect":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        text = req.get("text", "")
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        result = detect(text, req.get("context"))
        print(json.dumps(result, ensure_ascii=False))
        return 0

    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
