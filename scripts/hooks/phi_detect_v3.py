#!/usr/bin/env python3
"""
phi_detect_v3.py · v2.2 Hook 升级
====================================
基于 phi-detector v3（含上下文 / 占位符 / 日志时间戳过滤）。

v3 改进:
1. session 级去重：同 prompt 短时间内重复扫描跳过（cache 60s）
2. 误判反馈通道：阻断时输出"申诉链接"提示
3. 调用 phi-detector v3 替代 v2
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
PHI_DETECTOR_BIN = os.environ.get(
    "PHI_DETECTOR_BIN",
    str(PROJECT_DIR / "mcp" / "phi-detector" / "server_v3.py"),
)
AUDIT_LOG_BIN = str(PROJECT_DIR / "mcp" / "audit-log" / "server.py")
HOOK_MODE = os.environ.get("CLAUDE_HOOK_MODE", "warn")
CACHE_DIR = PROJECT_DIR / ".audit" / "_hook_cache"
CACHE_TTL_SEC = 60


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_check(text: str) -> dict | None:
    """v3 新增：session 级去重缓存"""
    if not CACHE_DIR.exists():
        return None
    h = _prompt_hash(text)
    cache_file = CACHE_DIR / f"{h}.json"
    if not cache_file.exists():
        return None
    try:
        if time.time() - cache_file.stat().st_mtime > CACHE_TTL_SEC:
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cache_save(text: str, result: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = _prompt_hash(text)
    (CACHE_DIR / f"{h}.json").write_text(json.dumps(result, ensure_ascii=False),
                                         encoding="utf-8")


def call_detector(text: str) -> dict:
    # 先查 cache
    cached = _cache_check(text)
    if cached is not None:
        return {**cached, "_from_cache": True}
    try:
        p = subprocess.run(
            ["python3", PHI_DETECTOR_BIN, "detect"],
            input=json.dumps({"text": text}, ensure_ascii=False),
            capture_output=True, text=True, timeout=2,
        )
        if p.returncode != 0:
            return {"_fail_closed": True, "stderr": p.stderr}
        result = json.loads(p.stdout)
        _cache_save(text, result)
        return result
    except Exception as e:
        return {"_fail_closed": True, "error": str(e)}


def call_audit_append(event_type: str, payload: dict) -> None:
    try:
        subprocess.run(
            ["python3", AUDIT_LOG_BIN, "append"],
            input=json.dumps({
                "event_type": event_type,
                "change_id": payload.get("change_id") or os.environ.get("CLAUDE_ACTIVE_CHANGE", "unknown"),
                "summary": payload.get("summary", {}),
                "payload": payload,
            }, ensure_ascii=False),
            capture_output=True, text=True, timeout=2,
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
        "hook": "phi_detect_v3",
        "mode": HOOK_MODE,
        "prompt_len": len(prompt),
        "block": block,
        "fail_closed": fail_closed,
        "summary": summary,
        "session_id": payload.get("session_id"),
        "from_cache": result.get("_from_cache", False),
    }
    with open(log_dir / "hook_phi_detect.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if block:
        # v2.1 兜底：高严重等级即使 warn 模式也强制阻断
        severity = "high" if summary.get("max_confidence", 0) >= 0.9 else \
                   "medium" if summary.get("max_confidence", 0) >= 0.7 else "low"
        forced_block = (HOOK_MODE == "block") or (severity == "high")
        record["severity"] = severity
        record["forced_block_in_warn_mode"] = (severity == "high" and HOOK_MODE != "block")

        call_audit_append("phi_block", record)

        msg = {
            "decision": "block",
            "reason": "phi_in_prompt" if not fail_closed else "phi_detector_unavailable_fail_closed",
            "severity": severity,
            "hook_mode": HOOK_MODE,
            "suppressed": result.get("suppressed", []),  # v3 新增：显示被 v3 规则忽略的
            "summary": summary,
            "next_action": (
                "对含 PHI 的内容先经 phi-desensitize Skill 处理。"
                + (" [本次因严重等级 high 强制阻断]" if record["forced_block_in_warn_mode"] else "")
            ),
            "appeal_path": "governance/合规例外申请单.md",
            "appeal_template": f"hash={record.get('session_id','')}+{datetime.utcnow().date()}",
        }
        print(json.dumps(msg, ensure_ascii=False), file=sys.stderr)
        if forced_block:
            return 2
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
