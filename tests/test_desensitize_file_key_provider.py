from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "desensitize"))

from crypto_envelope import decrypt_mapping, encrypt_mapping  # noqa: E402
from key_provider import (  # noqa: E402
    ChangeId,
    EncryptionContext,
    KeyId,
    KeyNotFoundError,
    KeyPermissionError,
    MapId,
)
from key_provider.file_provider import FileKeyProvider  # noqa: E402


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _context(key_id: str = "active") -> EncryptionContext:
    return EncryptionContext(
        change_id=ChangeId("change-t2"),
        map_id=MapId("map-synthetic"),
        key_id=KeyId(key_id),
    )


def test_multi_generation_roundtrip_and_active_key(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")
    context = _context()
    records: list[tuple[int, str, bytes, str, object]] = []

    for generation in range(3):
        key_bytes = provider.rotate("active")
        ciphertext, metadata = encrypt_mapping(
            {"generation": str(generation)},
            key_bytes,
            context,
        )
        records.append((generation, f"generation-{generation}", key_bytes, ciphertext, metadata))

    assert provider.list_generations("active") == [0, 1, 2]
    assert provider.get_key("active") == records[-1][2]
    assert provider.get_key_by_generation("active", 2) == records[-1][2]

    for generation, _label, _key_bytes, ciphertext, metadata in records:
        restored = decrypt_mapping(
            ciphertext,
            metadata,
            provider.get_key_by_generation("active", generation),
            context,
        )
        assert restored == {"generation": str(generation)}


def test_legacy_file_auto_migrates_to_generation_zero(tmp_path: Path) -> None:
    root = tmp_path / "keystore"
    root.mkdir(parents=True)
    legacy_path = root / "legacy.key"
    legacy_bytes = b"l" * 32
    legacy_path.write_bytes(legacy_bytes)
    os.chmod(legacy_path, 0o400)

    provider = FileKeyProvider(root)

    assert provider.get_key("legacy") == legacy_bytes
    assert not legacy_path.exists()
    assert (root / "legacy.0.key").exists()

    next_key = provider.rotate("legacy")
    assert len(next_key) == 32
    assert provider.list_generations("legacy") == [0, 1]
    assert provider.get_key_by_generation("legacy", 0) == legacy_bytes
    assert provider.get_key_by_generation("legacy", 1) == next_key


def test_max_generations_prunes_oldest_generation(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore", max_generations=3)

    keys = [provider.rotate("pruned") for _ in range(4)]

    assert provider.list_generations("pruned") == [1, 2, 3]
    assert provider.get_key("pruned") == keys[-1]
    with pytest.raises(KeyNotFoundError):
        provider.get_key_by_generation("pruned", 0)
    assert not (tmp_path / "keystore" / "pruned.0.key").exists()


def test_rotate_get_key_roundtrip_and_permissions(tmp_path: Path) -> None:
    root = tmp_path / "keystore"
    provider = FileKeyProvider(root)

    key_bytes = provider.rotate("active")
    key_path = root / "active.0.key"

    assert len(key_bytes) == 32
    assert key_path.exists()
    assert _mode(root) == 0o700
    assert _mode(key_path) == 0o400
    assert provider.get_key("active") == key_bytes


def test_get_key_rejects_world_readable_file(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")
    provider.rotate("active")
    key_path = tmp_path / "keystore" / "active.0.key"

    os.chmod(key_path, 0o644)

    with pytest.raises(KeyPermissionError, match="permissions"):
        provider.get_key("active")


def test_symlink_generation_file_is_rejected(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")
    target = tmp_path / "keystore" / "target.bin"
    target.write_bytes(b"t" * 32)
    os.chmod(target, 0o400)
    provider.rotate("linked")
    active_path = tmp_path / "keystore" / "linked.0.key"
    os.unlink(active_path)
    active_path.symlink_to(target)

    with pytest.raises(KeyPermissionError, match="regular file"):
        provider.get_key("linked")


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
    (root / "alpha.0.key.tmp").write_text("ignore-me", encoding="utf-8")

    assert provider.list_keys() == [KeyId("alpha"), KeyId("beta")]


def test_invalid_key_id_fails_closed(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")

    with pytest.raises(KeyPermissionError, match="invalid key id"):
        provider.rotate("../escape")


def test_malformed_key_file_does_not_leak_key_bytes(tmp_path: Path) -> None:
    root = tmp_path / "keystore"
    provider = FileKeyProvider(root)
    key_path = root / "broken.0.key"
    key_path.write_bytes(b"LEAK-ME-DO-NOT-PROCESS")
    os.chmod(key_path, 0o400)

    with pytest.raises(KeyPermissionError) as excinfo:
        provider.get_key("broken")

    assert "LEAK-ME" not in str(excinfo.value)
