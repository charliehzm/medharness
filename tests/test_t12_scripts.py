from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BACKUP = SCRIPTS / "backup.sh"
RESTORE = SCRIPTS / "restore.sh"
UPGRADE = SCRIPTS / "upgrade.sh"
TEARDOWN = SCRIPTS / "teardown.sh"
HASHCHAIN = ROOT / "mcp" / "audit-log" / "hashchain.py"
T12_SCRIPTS = (BACKUP, RESTORE, UPGRADE, TEARDOWN)

spec = util.spec_from_file_location("t12_hashchain_helper", HASHCHAIN)
assert spec is not None
hashchain = util.module_from_spec(spec)
sys.modules["t12_hashchain_helper"] = hashchain
assert spec.loader is not None
spec.loader.exec_module(hashchain)


def _run(cmd: list[str], *, env: dict[str, str] | None = None, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False, env=merged_env)


def _gpg_available() -> bool:
    return shutil.which("gpg") is not None


def _event(row_id: int) -> dict[str, object]:
    return {
        "event_id": f"evt-t12-{row_id:04d}",
        "timestamp": "2026-05-27T00:00:00.000Z",
        "actor": {
            "agent_role": "coder",
            "model_id": "synthetic-model",
            "vendor_family": "synthetic",
            "session_id": "synthetic-session",
        },
        "action": {"tool": "backup", "skill": None, "operation": "write"},
        "context": {"change_id": "feat/T12.3", "step": 12, "data_levels": ["L1"]},
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


def _fixture_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    audit_dir = tmp_path / "audit"
    keystore_dir = tmp_path / "keystore"
    backup_dir = tmp_path / "backups"
    audit_dir.mkdir()
    keystore_dir.mkdir()
    backup_dir.mkdir()
    _write_jsonl(audit_dir / "audit_log_export.jsonl", _build_chain(3))
    (audit_dir / "audit-note.txt").write_text("synthetic audit metadata\n", encoding="utf-8")
    (keystore_dir / "mapping-key.txt").write_text("synthetic keystore material\n", encoding="utf-8")
    return audit_dir, keystore_dir, backup_dir


def _run_backup(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    audit_dir, keystore_dir, backup_dir = _fixture_dirs(tmp_path)
    proc = _run(
        [
            "bash",
            str(BACKUP),
            "--audit-dir",
            str(audit_dir),
            "--keystore-dir",
            str(keystore_dir),
            "--out",
            str(backup_dir),
        ],
        env={"MEDHARNESS_BACKUP_PASSPHRASE": "synthetic-passphrase"},
    )
    return proc, audit_dir, keystore_dir, backup_dir


def _backup_file(backup_dir: Path) -> Path:
    matches = sorted(backup_dir.glob("medharness-backup-*.tar.gz.gpg"))
    assert len(matches) == 1
    return matches[0]


def test_backup_script_exists_and_executable() -> None:
    assert BACKUP.exists()
    assert os.access(BACKUP, os.X_OK)
    assert BACKUP.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_restore_script_exists_and_executable() -> None:
    assert RESTORE.exists()
    assert os.access(RESTORE, os.X_OK)
    assert RESTORE.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_backup_uses_strict_mode() -> None:
    assert "set -euo pipefail" in BACKUP.read_text(encoding="utf-8")


@pytest.mark.skipif(not _gpg_available(), reason="gpg is required for backup/restore tests")
def test_backup_creates_tar_gz_gpg_with_sha256(tmp_path: Path) -> None:
    proc, _audit_dir, _keystore_dir, backup_dir = _run_backup(tmp_path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    backup = _backup_file(backup_dir)
    assert backup.name.endswith(".tar.gz.gpg")
    assert (backup_dir / f"{backup.name}.sha256").exists()
    assert "Backup complete" in proc.stdout


@pytest.mark.skipif(not _gpg_available(), reason="gpg is required for backup/restore tests")
def test_restore_roundtrip_recovers_data(tmp_path: Path) -> None:
    proc, audit_dir, keystore_dir, backup_dir = _run_backup(tmp_path)
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()

    restore = _run(
        ["bash", str(RESTORE), "--backup", str(_backup_file(backup_dir)), "--target-prefix", str(restore_dir)],
        env={"MEDHARNESS_BACKUP_PASSPHRASE": "synthetic-passphrase"},
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert restore.returncode == 0, restore.stdout + restore.stderr
    assert (restore_dir / "audit" / "audit_log_export.jsonl").read_text(encoding="utf-8") == (
        audit_dir / "audit_log_export.jsonl"
    ).read_text(encoding="utf-8")
    assert (restore_dir / "keystore" / "mapping-key.txt").read_text(encoding="utf-8") == (
        keystore_dir / "mapping-key.txt"
    ).read_text(encoding="utf-8")
    assert "Hashchain verified" in restore.stdout


@pytest.mark.skipif(not _gpg_available(), reason="gpg is required for backup/restore tests")
def test_restore_verifies_sha256_when_present(tmp_path: Path) -> None:
    proc, _audit_dir, _keystore_dir, backup_dir = _run_backup(tmp_path)
    backup = _backup_file(backup_dir)
    with backup.open("ab") as fh:
        fh.write(b"tamper")

    restore = _run(
        ["bash", str(RESTORE), "--backup", str(backup), "--target-prefix", str(tmp_path / "restored")],
        env={"MEDHARNESS_BACKUP_PASSPHRASE": "synthetic-passphrase"},
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert restore.returncode == 5
    assert "sha256" in (restore.stdout + restore.stderr)


def test_backup_rejects_missing_source_dirs(tmp_path: Path) -> None:
    proc = _run(
        [
            "bash",
            str(BACKUP),
            "--audit-dir",
            str(tmp_path / "missing-audit"),
            "--keystore-dir",
            str(tmp_path / "missing-keystore"),
            "--out",
            str(tmp_path / "backups"),
        ],
        env={"MEDHARNESS_BACKUP_PASSPHRASE": "synthetic-passphrase"},
    )

    assert proc.returncode == 2
    assert "audit dir missing" in proc.stderr


def test_backup_rejects_missing_passphrase(tmp_path: Path) -> None:
    audit_dir, keystore_dir, backup_dir = _fixture_dirs(tmp_path)
    env = os.environ.copy()
    env.pop("MEDHARNESS_BACKUP_PASSPHRASE", None)
    proc = subprocess.run(
        [
            "bash",
            str(BACKUP),
            "--audit-dir",
            str(audit_dir),
            "--keystore-dir",
            str(keystore_dir),
            "--out",
            str(backup_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    assert proc.returncode == 6
    assert "passphrase not provided" in proc.stderr


def test_upgrade_script_exists_and_executable() -> None:
    assert UPGRADE.exists()
    assert os.access(UPGRADE, os.X_OK)
    assert UPGRADE.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_teardown_script_exists_and_executable() -> None:
    assert TEARDOWN.exists()
    assert os.access(TEARDOWN, os.X_OK)
    assert TEARDOWN.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_upgrade_returns_zero_for_first_release() -> None:
    proc = _run(["bash", str(UPGRADE)])

    assert proc.returncode == 0
    assert "first release" in proc.stdout
    assert "no upgrade needed" in proc.stdout


def test_upgrade_returns_one_for_unknown_path() -> None:
    proc = _run(["bash", str(UPGRADE), "--from", "0.5.0-edge", "--to", "0.7.0"])

    assert proc.returncode == 1
    assert "unknown upgrade path" in proc.stderr


def test_teardown_dry_run_does_not_execute() -> None:
    proc = _run(["bash", str(TEARDOWN), "--dry-run", "--force"])

    assert proc.returncode == 0
    assert "Teardown plan" in proc.stdout
    assert "[DRY RUN]" in proc.stdout
    assert "Starting teardown" not in proc.stdout


def test_teardown_lists_data_dirs_in_purge_plan() -> None:
    proc = _run(["bash", str(TEARDOWN), "--dry-run", "--purge-data", "--force"])

    assert proc.returncode == 0
    assert "/data/medharness/audit" in proc.stdout
    assert "/data/medharness/keystore" in proc.stdout
    assert "/data/medharness/clickhouse" in proc.stdout
    assert "/var/medharness/backups" in proc.stdout


def test_teardown_help_documents_purge_data_warning() -> None:
    proc = _run(["bash", str(TEARDOWN), "--help"])

    assert proc.returncode == 0
    assert "--purge-data" in proc.stdout
    assert "dangerous" in proc.stdout
    assert "preserve /data/medharness/* data" in proc.stdout


def test_all_t12_scripts_use_strict_mode() -> None:
    for script in T12_SCRIPTS:
        assert "set -euo pipefail" in script.read_text(encoding="utf-8")


def test_all_t12_scripts_have_proper_file_mode() -> None:
    for script in T12_SCRIPTS:
        assert os.access(script, os.X_OK)
        mode = stat.S_IMODE(script.stat().st_mode)
        assert mode & 0o755 == 0o755


def test_no_t12_script_logs_phi_or_secrets() -> None:
    forbidden = ("prompt=", "secret=", "token=", "password=")
    for script in T12_SCRIPTS:
        text = script.read_text(encoding="utf-8").lower()
        for sentinel in forbidden:
            assert sentinel not in text, f"{script.name} contains forbidden sentinel: {sentinel}"
