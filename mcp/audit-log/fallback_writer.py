from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class FallbackWriterContract(Exception):
    """Raised when caller passes event missing chain fields."""


class FallbackLockHeld(Exception):
    """Raised when PID lock is held by another process."""


class FileFallbackWriter:
    """Append fallback JSONL when ClickHouse unavailable."""

    REQUIRED_CHAIN_FIELDS = ("event_id", "row_id", "prev_hash", "current_hash")

    def __init__(self, base_dir: Path, lock_acquire: bool = True) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._base_dir / "fallback.pid"
        self._lock_acquired = False
        self._fallback_path = self._base_dir / f"audit-fallback-{int(time.time())}.jsonl"
        if lock_acquire:
            self._acquire_lock()

    def _acquire_lock(self) -> None:
        if self._lock_path.exists():
            try:
                held_pid = int(self._lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                held_pid = -1
            if held_pid > 0 and self._pid_alive(held_pid):
                raise FallbackLockHeld(f"lock held by alive pid {held_pid}")
        self._lock_path.write_text(str(os.getpid()), encoding="utf-8")
        self._lock_acquired = True

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError, OSError):
            return False
        return True

    def release_lock(self) -> None:
        if self._lock_acquired and self._lock_path.exists():
            self._lock_path.unlink()
        self._lock_acquired = False

    def _validate_event(self, event: dict[str, Any]) -> None:
        missing = [field for field in self.REQUIRED_CHAIN_FIELDS if field not in event]
        if missing:
            joined = ", ".join(missing)
            raise FallbackWriterContract(f"event missing chain field(s): {joined}")
        if "prompt" in event or "raw_text" in event:
            raise FallbackWriterContract("event contains forbidden raw text field")

    def append(self, event_with_hash: dict[str, Any]) -> dict[str, Any]:
        self._validate_event(event_with_hash)
        line = json.dumps(event_with_hash, ensure_ascii=False, sort_keys=True)
        with self._fallback_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return {
            "event_id": event_with_hash["event_id"],
            "row_id": event_with_hash["row_id"],
            "prev_hash": event_with_hash["prev_hash"],
            "current_hash": event_with_hash["current_hash"],
            "fallback_path": str(self._fallback_path),
        }

    def list_pending(self) -> list[Path]:
        files = [
            path
            for path in sorted(self._base_dir.glob("audit-fallback-*.jsonl"))
            if not path.name.endswith(".replayed")
        ]
        return files

    def replay_iter(self, path: Path) -> Iterator[dict[str, Any]]:
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def mark_replayed(self, path: Path) -> None:
        replayed = path.with_name(path.name + ".replayed")
        path.rename(replayed)
