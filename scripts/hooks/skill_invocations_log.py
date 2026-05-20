#!/usr/bin/env python3
"""
skill_invocations_log.py · 采集 Skill 命中数据（M2 起接入）
============================================================
作为 UserPromptSubmit 与 Stop 两个 Hook 阶段的额外采集器，记录：
- 用户 prompt 中显式提到的 $skill-name
- 本次回合主线实际调用的 Skill（通过 stop_summary payload 推断）
- 后续由 Skill Owner 周报根据本日志计算"触发准确率"

落盘: .audit/skill_invocations.jsonl
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
LOG_PATH = PROJECT_DIR / ".audit" / "skill_invocations.jsonl"
SKILL_DIR = PROJECT_DIR / ".claude" / "skills"

SKILL_NAMES = set()
if SKILL_DIR.exists():
    for d in SKILL_DIR.iterdir():
        if d.is_dir() and (d / "SKILL.md").exists():
            SKILL_NAMES.add(d.name)


def detect_user_intent(prompt: str) -> list[str]:
    """从 prompt 中找用户显式调用的 $skill-name。"""
    hits = []
    for m in re.finditer(r"\$([a-z][a-z0-9-]+)", prompt or ""):
        name = m.group(1)
        if name in SKILL_NAMES:
            hits.append(name)
    return hits


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    hook = sys.argv[1] if len(sys.argv) > 1 else "user-prompt"
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": hook,
        "session_id": payload.get("session_id"),
        "turn_id": payload.get("turn_id"),
        "change_id": os.environ.get("CLAUDE_ACTIVE_CHANGE"),
    }

    if hook == "user-prompt":
        prompt = payload.get("prompt") or payload.get("user_input") or ""
        intents = detect_user_intent(prompt)
        record["user_explicit_skills"] = intents
    elif hook == "stop":
        # 由调用方注入 actual_skills_invoked（推断自 transcripts）
        record["actual_skills_invoked"] = payload.get("actual_skills_invoked", [])
        record["files_modified_count"] = payload.get("files_modified_count")
    else:
        record["raw_payload_keys"] = list(payload.keys())

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
