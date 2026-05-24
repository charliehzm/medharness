from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docker-build.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-build.yml"

ALL_MCPS = (
    "phi-detector",
    "desensitize",
    "model-router",
    "audit-log",
    "ci-trigger",
    "internal-kb",
    "pm-bridge",
    "vector-db",
)


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_script_exists_is_executable_and_has_shebang() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_script_is_bash_parseable() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_script_usage_path_is_sane_and_no_args_exits_2() -> None:
    result = subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)

    assert result.returncode == 2
    assert "Usage:" in (result.stdout + result.stderr)


def test_script_uses_strict_mode_and_repo_root_discovery() -> None:
    text = _script_text()

    assert "set -euo pipefail" in text
    assert "SCRIPT_DIR" in text
    assert "REPO_ROOT" in text
    assert "VERSION_FILE" in text


def test_script_lists_all_8_mcps_and_size_targets() -> None:
    text = _script_text()

    for mcp in ALL_MCPS:
        assert mcp in text
    assert "phi-detector|desensitize|model-router|audit-log" in text
    assert "ci-trigger|internal-kb|pm-bridge|vector-db" in text
    assert text.count("echo 500") == 1
    assert text.count("echo 200") == 1


def test_script_strips_version_trailing_newline() -> None:
    text = _script_text()

    assert "tr -d '\\n'" in text or "head -c -1" in text


def test_script_has_size_gate_and_non_root_smoke() -> None:
    text = _script_text()

    assert "SIZE_MB" in text
    assert "exit 5" in text
    assert "id" in text and "-u" in text
    assert "9000" in text
    assert "exit 6" in text


def test_script_builds_with_version_commit_args_and_json_report() -> None:
    text = _script_text()

    assert "--build-arg" in text
    assert "VERSION=" in text
    assert "GIT_COMMIT=" in text
    assert '"size_mb":' in text
    assert '"size_target_mb":' in text
    assert '"git_commit":' in text
    assert '"uid":' in text


def test_workflow_parses_and_matrix_covers_all_8_mcps() -> None:
    data = yaml.safe_load(_workflow_text())

    matrix = data["jobs"]["build-and-scan"]["strategy"]["matrix"]["mcp"]
    assert matrix == list(ALL_MCPS)


def test_workflow_uses_trivy_action_and_weekly_cron() -> None:
    text = _workflow_text()

    assert "aquasec/trivy-action" in text
    assert "HIGH,CRITICAL" in text
    assert "exit-code: '1'" in text
    assert "0 2 * * 1" in text


def test_workflow_builds_reports_and_reads_version() -> None:
    text = _workflow_text()

    assert "tr -d '\\n' < VERSION" in text
    assert "build-report-${{ matrix.mcp }}-${{ github.run_id }}" in text
    assert "/tmp/medharness-build/${{ matrix.mcp }}.json" in text
    assert "trivy-${{ matrix.mcp }}.sarif" in text
    assert "mcp-${{ matrix.mcp }}:${{ steps.version.outputs.value }}" in text
