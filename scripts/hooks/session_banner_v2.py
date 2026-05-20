#!/usr/bin/env python3
"""
SessionStart Hook v2.2 · 增强版 banner
========================================
v2.2 改进：
- 显示当前 SOP route (micro / full)
- 显示 Hook 模式 (warn / block)
- 显示本周已被阻断次数（让开发者知道当前合规状态）
- 显示开发者上次 NPS 得分
- 一键申诉路径
"""
from __future__ import annotations
import json, os, re, sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def find_active_change() -> Path | None:
    env = os.environ.get("CLAUDE_ACTIVE_CHANGE")
    if env:
        p = PROJECT_DIR / "openspec" / "changes" / env
        return p if p.exists() else None
    base = PROJECT_DIR / "openspec" / "changes"
    if not base.exists():
        return None
    cs = [d for d in base.iterdir() if d.is_dir() and d.name != "archive"]
    return max(cs, key=lambda d: d.stat().st_mtime) if cs else None


def get_recent_blocks() -> int:
    p = PROJECT_DIR / ".audit" / "hook_phi_detect.jsonl"
    if not p.exists():
        return 0
    cutoff = datetime.utcnow() - timedelta(days=7)
    n = 0
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("block"):
                    ts = rec.get("ts", "")
                    if ts:
                        try:
                            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                            if t >= cutoff:
                                n += 1
                        except Exception:
                            pass
            except Exception:
                continue
    return n


def get_memory_health() -> str | None:
    curation = PROJECT_DIR / ".memory" / "curation"
    if not curation.exists():
        return None
    rs = sorted(curation.glob("weekly_*.md"))
    if not rs:
        return None
    text = rs[-1].read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"Health score:\s*([\d.]+)", text)
    return m.group(1) if m else None


def main() -> int:
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    change = find_active_change()
    hook_mode = os.environ.get("CLAUDE_HOOK_MODE", "warn")
    blocks_7d = get_recent_blocks()
    health = get_memory_health()

    tier = "—"
    signer = "未签字"
    if change:
        tag = change / "COMPLIANCE_TAG.md"
        if tag.exists():
            text = tag.read_text(encoding="utf-8")
            m = re.search(r"\*\*最高等级\*\*：`(L[1-4])`", text)
            if m:
                tier = m.group(1)
            m2 = re.search(r"Compliance Officer 签字\s*\|\s*`([^`]+)`", text)
            if m2 and not m2.group(1).startswith("<"):
                signer = m2.group(1).strip()

    lines = [
        "═══════════════════════════════════════════════════════════════════",
        "  Claude Code · 医疗数据 SaaS 体系 · v2.2",
        "─────────────────────────────────────────────────────────────────────",
        f"  活跃 change   : {change.name if change else '(无 · pre-step-0)'}",
        f"  数据等级      : {tier}    合规签字 : {signer}",
        f"  Hook Mode     : {hook_mode}    近 7 天阻断 : {blocks_7d} 次",
    ]
    if health:
        lines.append(f"  Memory 健康   : {health} (目标 ≥ 0.92)")
    lines.extend([
        "─────────────────────────────────────────────────────────────────────",
        "  快速路由提示:",
        "    micro change (改 ≤ 2 文件): `$quick-fix`",
        "    feature work:               `$prd-implementation-precheck`",
        "    debugging:                  `$systematic-debugging`",
        "  Hook 误阻断申诉: governance/合规例外申请单.md",
        "═══════════════════════════════════════════════════════════════════",
    ])
    print("\n".join(lines))

    # 落审计
    log_dir = PROJECT_DIR / ".audit"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "session_starts.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.utcnow().isoformat() + "Z",
            "change": change.name if change else None,
            "tier": tier,
            "hook_mode": hook_mode,
            "blocks_7d": blocks_7d,
            "memory_health": health,
        }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
