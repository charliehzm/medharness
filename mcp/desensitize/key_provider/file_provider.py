"""File-backed KeyProvider for T2.4.

This provider stores generation-based keys on disk. T2.3's single-file layout
is still supported as a migration source and will be promoted to generation 0
on first access.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from key_provider import KeyId, KeyNotFoundError, KeyPermissionError, KeyProvider

KEY_BYTES = 32
KEY_FILE_SUFFIX = ".key"
DEFAULT_MAX_GENERATIONS = 6
SAFE_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GEN_FILE_RE = re.compile(r"^(?P<key_id>[A-Za-z0-9][A-Za-z0-9._-]*)\.(?P<gen>\d+)\.key$")


def _default_keystore_root() -> Path:
    configured = os.environ.get("MEDHARNESS_KEYSTORE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".medharness" / "keystore"


def _sanitize_key_id(key_id: KeyId | str) -> str:
    value = str(key_id)
    if not value or value in {".", ".."}:
        raise KeyPermissionError("invalid key id")
    if value != Path(value).name:
        raise KeyPermissionError("invalid key id")
    if "\x00" in value or not SAFE_KEY_ID_RE.match(value):
        raise KeyPermissionError("invalid key id")
    return value


def _is_legacy_key_file_name(name: str) -> bool:
    if not name.endswith(KEY_FILE_SUFFIX):
        return False
    if GEN_FILE_RE.match(name):
        return False
    base = name[: -len(KEY_FILE_SUFFIX)]
    return bool(base) and bool(SAFE_KEY_ID_RE.match(base))


class FileKeyProvider(KeyProvider):
    """Local file-backed key provider with generation retention."""

    def __init__(
        self,
        keystore_root: str | Path | None = None,
        max_generations: int = DEFAULT_MAX_GENERATIONS,
    ) -> None:
        if max_generations < 1:
            raise ValueError("max_generations must be >= 1")
        self._root = (
            Path(keystore_root).expanduser()
            if keystore_root is not None
            else _default_keystore_root()
        )
        self._max_generations = max_generations
        self._ensure_root()

    @property
    def max_generations(self) -> int:
        return self._max_generations

    def _ensure_root(self) -> None:
        if self._root.exists() and not self._root.is_dir():
            raise KeyPermissionError("keystore root is not a directory")
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            self._root.chmod(0o700)
        except OSError as exc:  # pragma: no cover - platform-specific
            raise KeyPermissionError("unable to secure keystore root") from exc

    def _legacy_path(self, safe_key_id: str) -> Path:
        return self._root / f"{safe_key_id}{KEY_FILE_SUFFIX}"

    def _generation_path(self, safe_key_id: str, generation: int) -> Path:
        return self._root / f"{safe_key_id}.{generation}.key"

    def _ensure_secure_key_file(self, path: Path) -> None:
        if path.is_symlink():
            raise KeyPermissionError("key file is not a regular file")
        try:
            stat_result = path.stat()
        except FileNotFoundError as exc:
            raise KeyNotFoundError("key not found") from exc
        except OSError as exc:
            raise KeyPermissionError("unable to stat key file") from exc

        if not path.is_file():
            raise KeyPermissionError("key file is not a regular file")

        mode = stat.S_IMODE(stat_result.st_mode)
        if mode > 0o600:
            raise KeyPermissionError("key file permissions are too broad")

    def _read_key(self, path: Path) -> bytes:
        self._ensure_secure_key_file(path)
        try:
            key_bytes = path.read_bytes()
        except FileNotFoundError as exc:
            raise KeyNotFoundError("key not found") from exc
        except OSError as exc:
            raise KeyPermissionError("unable to read key file") from exc

        if len(key_bytes) != KEY_BYTES:
            raise KeyPermissionError("invalid key file length")
        return key_bytes

    def _write_key(self, path: Path, key_bytes: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=self._root, prefix=".tmp-", suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(key_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_path, 0o400)
            os.replace(tmp_path, path)
            if stat.S_IMODE(path.stat().st_mode) != 0o400:
                raise KeyPermissionError("key file permissions are not 0400")
        except Exception:
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            raise

    def _migrate_legacy_key_file(self, safe_key_id: str) -> None:
        legacy_path = self._legacy_path(safe_key_id)
        if not legacy_path.exists():
            return
        generation_zero_path = self._generation_path(safe_key_id, 0)
        if generation_zero_path.exists():
            return
        self._ensure_secure_key_file(legacy_path)
        try:
            os.replace(legacy_path, generation_zero_path)
            os.chmod(generation_zero_path, 0o400)
        except OSError as exc:
            raise KeyPermissionError("unable to migrate legacy key file") from exc
        if stat.S_IMODE(generation_zero_path.stat().st_mode) != 0o400:
            raise KeyPermissionError("key file permissions are not 0400")

    def _generation_map(self, key_id: KeyId | str) -> dict[int, Path]:
        safe_key_id = _sanitize_key_id(key_id)
        self._migrate_legacy_key_file(safe_key_id)
        generations: dict[int, Path] = {}
        for path in sorted(self._root.iterdir(), key=lambda item: item.name):
            if not path.is_file() and not path.is_symlink():
                continue
            match = GEN_FILE_RE.match(path.name)
            if not match or match.group("key_id") != safe_key_id:
                continue
            generation = int(match.group("gen"))
            self._ensure_secure_key_file(path)
            generations[generation] = path
        return generations

    def _candidate_key_ids(self) -> set[str]:
        key_ids: set[str] = set()
        for path in sorted(self._root.iterdir(), key=lambda item: item.name):
            if not path.is_file() and not path.is_symlink():
                continue
            match = GEN_FILE_RE.match(path.name)
            if match:
                self._ensure_secure_key_file(path)
                key_ids.add(match.group("key_id"))
                continue
            if _is_legacy_key_file_name(path.name):
                self._ensure_secure_key_file(path)
                key_ids.add(path.name[: -len(KEY_FILE_SUFFIX)])
        return key_ids

    def _prune_old_generations(self, generations: dict[int, Path]) -> None:
        while len(generations) > self._max_generations:
            oldest_generation = min(generations)
            path = generations.pop(oldest_generation)
            self._ensure_secure_key_file(path)
            try:
                path.unlink()
            except FileNotFoundError as exc:
                raise KeyNotFoundError("key not found") from exc
            except OSError as exc:
                raise KeyPermissionError("unable to remove key file") from exc

    def get_key_by_generation(self, key_id: KeyId | str, generation: int) -> bytes:
        self._ensure_root()
        if not isinstance(generation, int) or generation < 0:
            raise KeyPermissionError("invalid generation")
        generations = self._generation_map(key_id)
        path = generations.get(generation)
        if path is None:
            raise KeyNotFoundError("key not found")
        return self._read_key(path)

    def list_generations(self, key_id: KeyId | str) -> list[int]:
        self._ensure_root()
        generations = self._generation_map(key_id)
        if not generations:
            raise KeyNotFoundError("key not found")
        return sorted(generations)

    def get_key(self, key_id: KeyId | str) -> bytes:
        generations = self._generation_map(key_id)
        if not generations:
            raise KeyNotFoundError("key not found")
        active_generation = max(generations)
        return self._read_key(generations[active_generation])

    def rotate(self, key_id: KeyId | str) -> bytes:
        self._ensure_root()
        safe_key_id = _sanitize_key_id(key_id)
        generations = self._generation_map(safe_key_id)
        next_generation = max(generations) + 1 if generations else 0
        key_bytes = secrets.token_bytes(KEY_BYTES)
        new_path = self._generation_path(safe_key_id, next_generation)
        self._write_key(new_path, key_bytes)
        generations[next_generation] = new_path
        self._prune_old_generations(generations)
        return key_bytes

    def list_keys(self) -> list[KeyId]:
        self._ensure_root()
        key_ids = self._candidate_key_ids()
        active_key_ids: list[KeyId] = []
        for key_id in sorted(key_ids):
            try:
                if self._generation_map(key_id):
                    active_key_ids.append(KeyId(key_id))
            except KeyNotFoundError:
                continue
        return active_key_ids
