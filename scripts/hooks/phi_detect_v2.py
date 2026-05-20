#!/usr/bin/env python3
"""
UserPromptSubmit Hook v2 · PHI 检测硬阻断（M3 起用）
=======================================================
与 v1 的差异：
- 调 mcp-phi-detector v2（含分类器层）
- 命中阻断（exit 2）+ stderr JSON 给用户解释
- 调 mcp-audit-log 记录阻断事件
- fail-closed：服务挂了 → 阻断（不放行）

环境切换：
  CLAUDE_HOOK_MODE=warn  → M2 占位模式（不阻断，仅警告）
  CLAUDE_HOOK_MODE=block → M3+ 默认（命中即阻断）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
PHI_DETECTOR_BIN = os.environ.get(
    "PHI_DETECTOR_BIN",
    str(PROJECT_DIR / "mcp" / "phi-detector" / "server_v2.py"),
)
AUDIT_LOG_BIN = os.environ.get(
    "AUDIT_LOG_BIN",
    str(PROJECT_DIR / "mcp" / "audit-log" / "server.py"),
)
HOOK_MODE = os.environ.get("CLAUDE_HOOK_MODE", "warn")


def call_detector(text: str) -> dict:
    try:
        p = subprocess.run(
            ["python3", PHI_DETECTOR_BIN, "detect"],
            input=json.dumps({"text": text}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode != 0:
            return {"_fail_closed": True, "stderr": p.stderr}
        return json.loads(p.stdout)
    except Exception as e:
        return {"_fail_closed": True, "error": str(e)}


def call_audit_append(event_type: str, payload: dict) -> None:
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

    prompt = payload.get("prompt") or payload.get("user_input") or ""
    result = call_detector(prompt)
    summary = result.get("summary", {})
    fail_closed = result.get("_fail_closed", False)
    block = bool(summary.get("blocking_recommendation") or fail_closed)

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "phi_detect_v2",
        "mode": HOOK_MODE,
        "prompt_len": len(prompt),
        "block": block,
        "fail_closed": fail_closed,
        "summary": summary,
        "session_id": payload.get("session_id"),
    }
    with open(log_dir / "hook_phi_detect.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if block:
        call_audit_append("phi_block", record)
        # v2.1 升级：高严重等级即使 warn 模式也强制阻断
        # 严重等级 = max_confidence 阈值
        severity = (
            "high"
            if summary.get("max_confidence", 0) >= 0.9
            else "medium"
            if summary.get("max_confidence", 0) >= 0.7
            else "low"
        )
        forced_block = (HOOK_MODE == "block") or (severity == "high")
        record["severity"] = severity
        record["forced_block_in_warn_mode"] = severity == "high" and HOOK_MODE != "block"
        msg = {
            "decision": "block",
            "reason": "phi_in_prompt"
            if not fail_closed
            else "phi_detector_unavailable_fail_closed",
            "severity": severity,
            "hook_mode": HOOK_MODE,
            "summary": summary,
            "next_action": "对含 PHI 的内容先经 phi-desensitize Skill 处理，再提交。"
            + (" [本次因严重等级 high 强制阻断]" if record["forced_block_in_warn_mode"] else ""),
        }
        print(json.dumps(msg, ensure_ascii=False), file=sys.stderr)
        if forced_block:
            return 2  # 硬阻断（含 warn 模式下的 high 兜底）
        return 0  # warn 模式 medium/low 仅打 stderr

    return 0


if __name__ == "__main__":
    sys.exit(main())
