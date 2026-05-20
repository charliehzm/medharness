#!/usr/bin/env python3
"""
SessionStart Hook · 会话起始横幅
==================================
作用：会话开始时打印当前 change 的合规上下文，让开发者一眼看到要遵守什么。

显示：
  - 活跃 change（如有）
  - 数据等级 + 模型 allowlist 摘要
  - 本周 Memory 健康分（如最近有周报）
  - 当前未签字 / 待处理高风险（如有）
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


def parse_tag_summary(tag_path: Path) -> dict:
    if not tag_path.exists():
        return {}
    text = tag_path.read_text(encoding="utf-8")
    m_tier = re.search(r"\*\*最高等级\*\*：`(L[1-4])`", text)
    m_sign = re.search(r"Compliance Officer 签字\s*\|\s*`([^`]+)`", text)
    return {
        "tier": m_tier.group(1) if m_tier else "?",
        "signed_by": (m_sign.group(1).strip() if m_sign else ""),
    }


def latest_memory_health(project_dir: Path) -> str | None:
    curation_dir = project_dir / ".memory" / "curation"
    if not curation_dir.exists():
        return None
    reports = sorted(curation_dir.glob("weekly_*.md"))
    if not reports:
        return None
    text = reports[-1].read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"Health score:\s*([\d.]+)", text)
    return m.group(1) if m else None


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    log_dir = project_dir / ".audit"
    log_dir.mkdir(exist_ok=True)

    try:
        json.load(sys.stdin)
    except Exception:
        pass

    change = find_active_change(project_dir)
    summary = parse_tag_summary(change / "COMPLIANCE_TAG.md") if change else {}
    health = latest_memory_health(project_dir)

    lines = ["=" * 60]
    lines.append("Claude Code · 医疗数据 SaaS 企业合规模式 (M1-placeholder)")
    lines.append("-" * 60)
    if change:
        lines.append(f"活跃 change : {change.name}")
        lines.append(f"数据等级    : {summary.get('tier', '?')}")
        signer = summary.get("signed_by", "")
        if signer and "<" not in signer:
            lines.append(f"合规签字    : {signer}")
        else:
            lines.append("合规签字    : ⚠️  未签字 / 占位 — 请先完成 Step 0")
    else:
        lines.append("活跃 change : (无 · pre-step-0)")
    if health:
        lines.append(f"Memory 健康 : {health}（目标 ≥ 0.95）")
    lines.append("-" * 60)
    lines.append("禁区提醒：L3/L4 字段入 prompt 前必须经 phi-desensitize")
    lines.append("=" * 60)
    print("\n".join(lines))

    # 同时记录到审计
    with open(log_dir / "session_starts.jsonl", "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "change": change.name if change else None,
                    "tier": summary.get("tier"),
                    "memory_health": health,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
