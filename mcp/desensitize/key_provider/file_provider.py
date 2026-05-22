"""File-backed KeyProvider for T2.3.

This is the naive single-generation provider. T2.4 will add active generations
and old-key retention; this leaf only guarantees secure local file custody.
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
SAFE_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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


class FileKeyProvider(KeyProvider):
    """Local file-backed key provider.

    The provider stores raw 32-byte keys in ``<key_id>.key`` files under a
    configurable keystore root. ``rotate`` overwrites the active key file in
    place for T2.3; T2.4 adds multi-generation retention.
    """

    def __init__(self, keystore_root: str | Path | None = None) -> None:
        self._root = (
            Path(keystore_root).expanduser()
            if keystore_root is not None
            else _default_keystore_root()
        )
        self._ensure_root()

    def _ensure_root(self) -> None:
        if self._root.exists() and not self._root.is_dir():
            raise KeyPermissionError("keystore root is not a directory")
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            self._root.chmod(0o700)
        except OSError as exc:  # pragma: no cover - platform-specific
            raise KeyPermissionError("unable to secure keystore root") from exc

    def _key_path(self, key_id: KeyId | str) -> Path:
        safe_key_id = _sanitize_key_id(key_id)
        return self._root / f"{safe_key_id}{KEY_FILE_SUFFIX}"

    def _ensure_secure_key_file(self, path: Path) -> None:
        try:
            stat_result = path.stat()
        except FileNotFoundError as exc:
            raise KeyNotFoundError("key not found") from exc
        except OSError as exc:
            raise KeyPermissionError("unable to stat key file") from exc

        if not path.is_file() or path.is_symlink():
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

    def get_key(self, key_id: KeyId | str) -> bytes:
        self._ensure_root()
        path = self._key_path(key_id)
        if not path.exists():
            raise KeyNotFoundError("key not found")
        return self._read_key(path)

    def rotate(self, key_id: KeyId | str) -> bytes:
        self._ensure_root()
        path = self._key_path(key_id)
        key_bytes = secrets.token_bytes(KEY_BYTES)
        self._write_key(path, key_bytes)
        return key_bytes

    def list_keys(self) -> list[KeyId]:
        self._ensure_root()
        keys: list[KeyId] = []
        for path in sorted(self._root.glob(f"*{KEY_FILE_SUFFIX}"), key=lambda item: item.name):
            if not path.is_file() or path.is_symlink():
                continue
            key_id = path.stem
            if SAFE_KEY_ID_RE.match(key_id):
                keys.append(KeyId(key_id))
        return keys
