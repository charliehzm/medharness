from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "scripts" / "verify-hashchain.sh"
LOGIC = ROOT / "scripts" / "verify_hashchain_logic.py"
HASHCHAIN = ROOT / "mcp" / "audit-log" / "hashchain.py"

spec = util.spec_from_file_location("audit_log_hashchain_test_helper", HASHCHAIN)
assert spec is not None
hashchain = util.module_from_spec(spec)
sys.modules["audit_log_hashchain_test_helper"] = hashchain
assert spec.loader is not None
spec.loader.exec_module(hashchain)


def _event(row_id: int) -> dict[str, object]:
    return {
        "event_id": f"evt-{row_id:04d}",
        "timestamp": "2026-05-24T03:00:00.000Z",
        "actor": {
            "agent_role": "coder",
            "model_id": "qwen-max",
            "vendor_family": "alibaba",
            "session_id": "s1",
        },
        "action": {"tool": "shell", "skill": None, "operation": "write"},
        "context": {"change_id": "feat/T4.7", "step": 6, "data_levels": ["L1"]},
        "result": {"status": "success", "reason": None, "duration_ms": 1.0},
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
        "row_id": row_id,
    }


def _build_chain(size: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    prev_hash = hashchain.GENESIS_PREV_HASH
    for row_id in range(size):
        event = _event(row_id)
        current_hash = hashchain.compute_hash(event, prev_hash)
        rows.append({**event, "prev_hash": prev_hash, "current_hash": current_hash})
        prev_hash = current_hash
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _run_logic(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LOGIC), "--input", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_shell(
    path: Path | None = None, env_override: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    cmd = ["bash", str(SHELL)]
    if path is not None:
        cmd.append(str(path))
    return subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)


def test_logic_returns_zero_for_intact_chain(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    _write_jsonl(path, _build_chain(100))

    proc = _run_logic(path)

    assert proc.returncode == 0
    assert json.loads(proc.stdout)["status"] == "ok"


def test_logic_returns_one_for_tampered_chain(tmp_path: Path) -> None:
    rows = _build_chain(100)
    rows[50]["result"]["status"] = "error"  # type: ignore[index]
    path = tmp_path / "tampered.jsonl"
    _write_jsonl(path, rows)

    proc = _run_logic(path)

    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["status"] == "tampered"
    assert report["broken_at_row_id"] == 50


def test_logic_returns_two_for_missing_input(tmp_path: Path) -> None:
    proc = _run_logic(tmp_path / "missing.jsonl")

    assert proc.returncode == 2
    assert "input file not found" in proc.stderr


def test_logic_returns_three_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{bad\n", encoding="utf-8")

    proc = _run_logic(path)

    assert proc.returncode == 3
    assert "failed to parse input" in proc.stderr


def test_logic_returns_zero_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    proc = _run_logic(path)

    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"status": "empty", "row_count": 0, "passed": True}


def test_logic_report_includes_row_count_and_broken_at(tmp_path: Path) -> None:
    rows = _build_chain(3)
    rows[2]["output_hash"] = "c" * 64
    path = tmp_path / "broken.jsonl"
    _write_jsonl(path, rows)

    proc = _run_logic(path)
    report = json.loads(proc.stdout)

    assert report["row_count"] == 3
    assert report["broken_at_row_id"] == 2
    assert report["passed"] is False


def test_shell_script_is_executable() -> None:
    assert SHELL.exists()
    assert SHELL.read_text(encoding="utf-8").startswith("#!")
    assert os.access(SHELL, os.X_OK)


def test_shell_script_passes_for_intact_chain(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    _write_jsonl(path, _build_chain(5))

    proc = _run_shell(path)

    assert proc.returncode == 0
    assert "hashchain verify PASSED" in proc.stdout


def test_shell_script_fails_for_tampered_chain(tmp_path: Path) -> None:
    rows = _build_chain(5)
    rows[1]["input_hash"] = "d" * 64
    path = tmp_path / "tampered.jsonl"
    _write_jsonl(path, rows)

    proc = _run_shell(path)

    assert proc.returncode == 1
    assert "SEV-1 alert" in proc.stderr


def test_shell_script_respects_env_var_override(tmp_path: Path) -> None:
    path = tmp_path / "env-chain.jsonl"
    _write_jsonl(path, _build_chain(2))

    proc = _run_shell(env_override={"VERIFY_HASHCHAIN_INPUT": str(path)})

    assert proc.returncode == 0
    assert str(path) in proc.stdout


def test_shell_script_uses_strict_mode() -> None:
    assert "set -euo pipefail" in SHELL.read_text(encoding="utf-8")
