#!/usr/bin/env python3
"""
Stop Hook · 回合结束汇总
==========================
作用：把本回合（一次 user prompt → assistant final response）的关键指标汇总落到
.audit/session_<id>.jsonl，作为 AUDIT_BUNDLE 的 prompts/ 原料。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    log_dir = project_dir / ".audit"
    log_dir.mkdir(exist_ok=True)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    session_id = payload.get("session_id", "unknown")
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "stop_summary",
        "phase": "M1-placeholder",
        "session_id": session_id,
        "turn_id": payload.get("turn_id"),
        "tool_calls_count": payload.get("tool_calls_count"),
        "files_modified": payload.get("files_modified"),
        "model_id": payload.get("model_id"),
        "prompt_tokens": payload.get("prompt_tokens"),
        "completion_tokens": payload.get("completion_tokens"),
    }

    out = log_dir / f"session_{session_id}.jsonl"
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
