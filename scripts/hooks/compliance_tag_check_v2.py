#!/usr/bin/env python3
"""
UserPromptSubmit Hook v2 · COMPLIANCE_TAG 强校验（M3 起用）
============================================================
与 v1 的差异：
- 走 audit-log append 记录阻断
- HOOK_MODE=block 时硬阻断
- 同时校验 MODEL_ALLOWLIST.json 的最少 schema（models / issued_by / valid_until）
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
AUDIT_LOG_BIN = str(PROJECT_DIR / "mcp" / "audit-log" / "server.py")
HOOK_MODE = os.environ.get("CLAUDE_HOOK_MODE", "warn")


def find_active_change() -> Path | None:
    env_change = os.environ.get("CLAUDE_ACTIVE_CHANGE")
    if env_change:
        p = PROJECT_DIR / "openspec" / "changes" / env_change
        return p if p.exists() else None
    base = PROJECT_DIR / "openspec" / "changes"
    if not base.exists():
        return None
    candidates = [d for d in base.iterdir() if d.is_dir()]
    return max(candidates, key=lambda d: d.stat().st_mtime) if candidates else None


def is_signed(tag: Path) -> bool:
    try:
        text = tag.read_text(encoding="utf-8")
    except Exception:
        return False
    m = re.search(r"Compliance Officer 签字\s*\|\s*`([^`]+)`", text)
    if not m:
        return False
    val = m.group(1).strip()
    return bool(val and not val.startswith("<") and "YYYY" not in val)


def validate_allowlist(al_path: Path) -> list[str]:
    try:
        data = json.loads(al_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"allowlist_invalid_json: {e}"]
    problems = []
    if "models" not in data:
        problems.append("allowlist_missing_models")
    if not data.get("issued_by"):
        problems.append("allowlist_missing_issuer")
    if not data.get("valid_until"):
        problems.append("allowlist_missing_validity")
    return problems


def call_audit(event_type: str, payload: dict) -> None:
    try:
        subprocess.run(
            ["python3", AUDIT_LOG_BIN, "append"],
            input=json.dumps({"event_type": event_type, "payload": payload}, ensure_ascii=False),
            capture_output=True, text=True, timeout=2,
        )
    except Exception:
        pass


def main() -> int:
    log_dir = PROJECT_DIR / ".audit"
    log_dir.mkdir(exist_ok=True)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    change = find_active_change()
    if change is None:
        return 0

    tag = change / "COMPLIANCE_TAG.md"
    allowlist = change / "MODEL_ALLOWLIST.json"

    problems = []
    if not tag.exists():
        problems.append(f"missing COMPLIANCE_TAG.md: {tag}")
    elif not is_signed(tag):
        problems.append(f"COMPLIANCE_TAG.md not signed: {tag}")
    if not allowlist.exists():
        problems.append(f"missing MODEL_ALLOWLIST.json: {allowlist}")
    else:
        problems.extend(validate_allowlist(allowlist))

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "compliance_tag_check_v2",
        "mode": HOOK_MODE,
        "change": str(change.relative_to(PROJECT_DIR)),
        "problems": problems,
    }
    with open(log_dir / "hook_compliance_tag_check.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if problems:
        call_audit("compliance_tag_block", record)
        msg = {
            "decision": "block",
            "reason": "step_0_incomplete",
            "problems": problems,
            "next_action": "先运行 compliance-precheck Skill 完成 Step 0。",
        }
        print(json.dumps(msg, ensure_ascii=False), file=sys.stderr)
        return 2 if HOOK_MODE == "block" else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
