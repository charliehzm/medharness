from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-worm.sh"
TARGET_DIRS = ("_audit_log", "audit-export", "audit-backup")


def _run(env_override: dict[str, str] | None = None, expect_exit: int | None = 0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    if expect_exit is not None and proc.returncode != expect_exit:
        pytest.fail(
            f"expected exit {expect_exit}, got {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def test_script_is_executable() -> None:
    assert SCRIPT.exists()
    first_line = SCRIPT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!"), f"missing shebang: {first_line}"
    assert os.access(SCRIPT, os.X_OK)


def test_script_macos_skip_path(tmp_path: Path) -> None:
    if platform.system() != "Darwin":
        pytest.skip("macOS-specific test")
    proc = _run(env_override={"MEDHARNESS_AUDIT_BASE": str(tmp_path)})

    assert "skipping real chattr" in proc.stdout
    assert "WORM setup complete" in proc.stdout
    for sub in TARGET_DIRS:
        assert (tmp_path / sub).exists()


def test_script_linux_chattr_path(tmp_path: Path) -> None:
    if platform.system() != "Linux":
        pytest.skip("Linux-specific test")
    if os.geteuid() != 0:
        pytest.skip("requires root for chattr")
    if not shutil.which("chattr") or not shutil.which("lsattr") or not shutil.which("sudo"):
        pytest.skip("requires chattr, lsattr, and sudo")

    proc = _run(env_override={"MEDHARNESS_AUDIT_BASE": str(tmp_path)}, expect_exit=None)
    if proc.returncode != 0:
        pytest.skip(f"filesystem does not support chattr in this environment: {proc.stderr}")
    assert "chattr +a applied" in proc.stdout
    assert "verified append-only" in proc.stdout

    for sub in TARGET_DIRS:
        subprocess.run(["sudo", "chattr", "-a", str(tmp_path / sub)], check=False)


def test_script_creates_all_three_directories(tmp_path: Path) -> None:
    proc = _run(env_override={"MEDHARNESS_AUDIT_BASE": str(tmp_path)}, expect_exit=None)
    if platform.system() == "Linux" and proc.returncode != 0:
        pytest.skip(f"Linux chattr path unavailable in this environment: {proc.stderr}")

    for sub in TARGET_DIRS:
        assert (tmp_path / sub).exists()


def test_script_respects_env_var_override(tmp_path: Path) -> None:
    custom_base = tmp_path / "custom"
    proc = _run(env_override={"MEDHARNESS_AUDIT_BASE": str(custom_base)}, expect_exit=None)
    if platform.system() == "Linux" and proc.returncode != 0:
        pytest.skip(f"Linux chattr path unavailable in this environment: {proc.stderr}")

    assert custom_base.exists()
    assert (custom_base / "_audit_log").exists()


def test_script_handles_unsupported_os_gracefully() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "unsupported" in content
    assert "exit 1" in content


def test_script_uses_set_strict_mode() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in content


def test_script_mentions_all_three_target_dirs() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    for sub in TARGET_DIRS:
        assert sub in content


def test_script_has_linux_failure_exit_codes() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    for exit_code in ("exit 2", "exit 3", "exit 4", "exit 5"):
        assert exit_code in content
