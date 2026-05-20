"""Smoke tests · 验证 v0.1.0-alpha 骨架完整性。

v0.2.0 起补充真实集成测试（Skill 触发 / MCP 路由 / Hook 拦截）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_files_present() -> None:
    """v0.1.0-alpha 根目录必备文件。"""
    required = [
        "README.md",
        "LICENSE",
        "LICENSE-CC-BY-SA-4.0",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "CLAUDE.md",
        "AGENTS.md",
        "HANDOFF.md",
        "研发交付SOP-v2.md",
        "研发交付SOP-v2.2-micro.md",
        "dryrun_e2e_v2.sh",
        "pyproject.toml",
        "requirements.txt",
        ".gitignore",
    ]
    for f in required:
        assert (ROOT / f).exists(), f"missing: {f}"


def test_skill_count() -> None:
    """23 Skill SKILL.md（5 合规 / 16 通用 / 2 micro 别名）。"""
    skills = list((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    assert len(skills) == 23, f"expected 23 skills, found {len(skills)}"


def test_sub_agent_count() -> None:
    """6 Sub-agent."""
    agents = list((ROOT / ".claude" / "sub_agents").glob("*.md"))
    assert len(agents) == 6, f"expected 6 sub-agents, found {len(agents)}"


def test_mcp_server_count() -> None:
    """8 MCP server."""
    expected = {
        "phi-detector",
        "desensitize",
        "model-router",
        "audit-log",
        "internal-kb",
        "vector-db",
        "ci-trigger",
        "pm-bridge",
    }
    found = {p.name for p in (ROOT / "mcp").iterdir() if p.is_dir()}
    assert expected.issubset(found), f"missing MCP servers: {expected - found}"


def test_hook_scripts_present() -> None:
    """9 Hook script."""
    hooks_dir = ROOT / "scripts" / "hooks"
    py_files = list(hooks_dir.glob("*.py"))
    assert len(py_files) >= 9, f"expected ≥9 hooks, found {len(py_files)}"


def test_compliance_red_lines_in_claude_md() -> None:
    """CLAUDE.md 必须含 5 条红线关键词。"""
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    must_have = ["PHI", "allowlist", "审计", "测试数据", "Hook"]
    for kw in must_have:
        assert kw in claude, f"missing red line keyword in CLAUDE.md: {kw}"


def test_example_change_complete() -> None:
    """示例 change 必备文件。"""
    change_dir = ROOT / "examples" / "示例-患者匹配最小可行版"
    assert (change_dir / "proposal.md").exists()
    assert (change_dir / "tasks.md").exists()
    assert (change_dir / "COMPLIANCE_TAG.md").exists()
    assert (change_dir / "specs" / "patient-match" / "spec.md").exists()


def test_license_apache_2() -> None:
    """LICENSE 必须是 Apache 2.0."""
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text
