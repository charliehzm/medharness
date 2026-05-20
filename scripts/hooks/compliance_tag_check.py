#!/usr/bin/env python3
"""
UserPromptSubmit Hook · COMPLIANCE_TAG 校验
=============================================
作用：当前会话所在的 change 必须有 COMPLIANCE_TAG.md，且已签字，且 MODEL_ALLOWLIST.json 存在。
否则阻断（M2 起）。M1 仅警告。

判断当前 change 的策略（M1 简化）：
  1. 通过环境变量 CLAUDE_ACTIVE_CHANGE（如果设置）
  2. 否则查找 openspec/changes/*/ 下最新修改的目录
  3. 都没有 → 跳过校验（无 change 上下文 = pre-step-0 状态）
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


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


def is_signed(tag_path: Path) -> bool:
    """简单签字检查：包含非 <...> 占位的签字字段。"""
    try:
        text = tag_path.read_text(encoding="utf-8")
    except Exception:
        return False
    m = re.search(r"Compliance Officer 签字\s*\|\s*`([^`]+)`", text)
    if not m:
        return False
    val = m.group(1).strip()
    return bool(val and not val.startswith("<") and "YYYY" not in val)


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    log_dir = project_dir / ".audit"
    log_dir.mkdir(exist_ok=True)

    # 吃掉 stdin
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    change = find_active_change(project_dir)
    if change is None:
        # 无活跃 change，跳过（pre-step-0）
        return 0

    tag = change / "COMPLIANCE_TAG.md"
    allowlist = change / "MODEL_ALLOWLIST.json"

    problems = []
    if not tag.exists():
        problems.append(f"缺失 COMPLIANCE_TAG.md: {tag}")
    elif not is_signed(tag):
        problems.append(f"COMPLIANCE_TAG.md 未签字: {tag}")
    if not allowlist.exists():
        problems.append(f"缺失 MODEL_ALLOWLIST.json: {allowlist}")

    log_line = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "hook": "compliance_tag_check",
        "phase": "M1-placeholder",
        "change": str(change.relative_to(project_dir)),
        "problems": problems,
    }
    with open(log_dir / "hook_compliance_tag_check.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_line, ensure_ascii=False) + "\n")

    if problems:
        print(
            "[Compliance Warning · M1 占位] 当前 change 未完成 Step 0:\n  - "
            + "\n  - ".join(problems)
            + "\nM2 起将硬阻断。请先运行 compliance-precheck Skill。",
            file=sys.stderr,
        )
        # M1 放行；M2 改 return 2
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
