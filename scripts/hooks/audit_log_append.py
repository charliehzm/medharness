#!/usr/bin/env python3
"""
PostToolUse Hook · 审计日志追加
==================================
作用：每次 tool 调用后，记录到本地 append-only JSONL，作为 AUDIT_BUNDLE 的原料。
M2 起：同时投递 mcp-audit-log（WORM）。

落盘位置：.audit/tool_calls.jsonl
轮转：单文件 > 50MB 时滚动到 .audit/tool_calls.<YYYY-MM-DD>.jsonl
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024


def rotate_if_needed(path: Path) -> Path:
    if path.exists() and path.stat().st_size > MAX_BYTES:
        stamp = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
        rotated = path.with_suffix(f".{stamp}.jsonl")
        path.rename(rotated)
    return path


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    log_dir = project_dir / ".audit"
    log_dir.mkdir(exist_ok=True)
    log_file = rotate_if_needed(log_dir / "tool_calls.jsonl")

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "audit_log_append",
        "phase": "M1-placeholder",
        "session_id": payload.get("session_id"),
        "tool_name": payload.get("tool_name"),
        "tool_input_preview": _safe_preview(payload.get("tool_input")),
        "tool_response_summary": _safe_preview(payload.get("tool_response"), limit=200),
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return 0


def _safe_preview(obj, limit: int = 500) -> str:
    if obj is None:
        return ""
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    if len(s) > limit:
        return s[:limit] + "...[truncated]"
    return s


if __name__ == "__main__":
    sys.exit(main())
