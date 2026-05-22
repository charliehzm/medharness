from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "desensitize"))

from key_provider import KeyId, KeyNotFoundError, KeyPermissionError  # noqa: E402
from key_provider.file_provider import FileKeyProvider  # noqa: E402


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_rotate_get_key_roundtrip_and_permissions(tmp_path: Path) -> None:
    root = tmp_path / "keystore"
    provider = FileKeyProvider(root)

    key_bytes = provider.rotate("active")
    key_path = root / "active.key"

    assert len(key_bytes) == 32
    assert key_path.exists()
    assert _mode(root) == 0o700
    assert _mode(key_path) == 0o400
    assert provider.get_key("active") == key_bytes


def test_rotate_overwrites_active_key_in_t2_3_naive_mode(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")

    first_key = provider.rotate("active")
    second_key = provider.rotate("active")

    assert len(second_key) == 32
    assert second_key != first_key
    assert provider.get_key("active") == second_key


def test_get_key_rejects_world_readable_file(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")
    provider.rotate("active")
    key_path = tmp_path / "keystore" / "active.key"

    os.chmod(key_path, 0o644)

    with pytest.raises(KeyPermissionError, match="permissions"):
        provider.get_key("active")


def test_missing_key_raises_not_found(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")

    with pytest.raises(KeyNotFoundError):
        provider.get_key("missing")


def test_list_keys_only_returns_key_files(tmp_path: Path) -> None:
    root = tmp_path / "keystore"
    provider = FileKeyProvider(root)
    provider.rotate("alpha")
    provider.rotate("beta")
    (root / "notes.txt").write_text("ignore-me", encoding="utf-8")
    (root / "alpha.key.tmp").write_text("ignore-me", encoding="utf-8")

    assert provider.list_keys() == [KeyId("alpha"), KeyId("beta")]


def test_invalid_key_id_fails_closed(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")

    with pytest.raises(KeyPermissionError, match="invalid key id"):
        provider.rotate("../escape")


def test_malformed_key_file_does_not_leak_key_bytes(tmp_path: Path) -> None:
    root = tmp_path / "keystore"
    provider = FileKeyProvider(root)
    key_path = root / "broken.key"
    key_path.write_bytes(b"LEAK-ME-DO-NOT-PROCESS")
    os.chmod(key_path, 0o400)

    with pytest.raises(KeyPermissionError) as excinfo:
        provider.get_key("broken")

    assert "LEAK-ME" not in str(excinfo.value)
