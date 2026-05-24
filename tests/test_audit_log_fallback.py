from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "audit-log"))

from fallback_writer import (  # noqa: E402
    FallbackLockHeld,
    FallbackWriterContract,
    FileFallbackWriter,
)


def _event(**overrides):
    event = {
        "event_id": "evt-0001",
        "row_id": 7,
        "prev_hash": "a" * 64,
        "current_hash": "b" * 64,
        "actor_agent_role": "coder",
        "action_tool": "shell",
    }
    event.update(overrides)
    return event


def test_init_creates_base_dir(tmp_path: Path) -> None:
    base_dir = tmp_path / "audit"

    writer = FileFallbackWriter(base_dir, lock_acquire=False)

    assert base_dir.exists()
    assert writer._base_dir == base_dir


def test_init_acquires_pid_lock(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)

    assert (tmp_path / "fallback.pid").exists()
    assert (tmp_path / "fallback.pid").read_text(encoding="utf-8").strip() == str(os.getpid())
    writer.release_lock()


def test_init_fails_when_lock_held_by_alive_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_path = tmp_path / "fallback.pid"
    lock_path.write_text("4242", encoding="utf-8")

    monkeypatch.setattr(FileFallbackWriter, "_pid_alive", staticmethod(lambda pid: True))

    with pytest.raises(FallbackLockHeld, match="lock held by alive pid 4242"):
        FileFallbackWriter(tmp_path)


def test_init_takes_over_stale_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_path = tmp_path / "fallback.pid"
    lock_path.write_text("4242", encoding="utf-8")

    monkeypatch.setattr(FileFallbackWriter, "_pid_alive", staticmethod(lambda pid: False))
    monkeypatch.setattr(os, "getpid", lambda: 9999)

    writer = FileFallbackWriter(tmp_path)

    assert lock_path.read_text(encoding="utf-8").strip() == "9999"
    writer.release_lock()


def test_append_writes_jsonl_with_chain_fields(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)

    result = writer.append(_event())

    assert result["event_id"] == "evt-0001"
    lines = (result["fallback_path"])
    assert Path(lines).exists()
    payload = Path(lines).read_text(encoding="utf-8").strip().splitlines()
    assert len(payload) == 1
    assert '"prev_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' in payload[0]
    writer.release_lock()


def test_append_appends_to_same_file_across_calls(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)

    first = writer.append(_event(event_id="evt-1"))
    second = writer.append(_event(event_id="evt-2"))

    assert first["fallback_path"] == second["fallback_path"]
    assert Path(first["fallback_path"]).read_text(encoding="utf-8").count("\n") == 2
    writer.release_lock()


def test_append_rejects_event_missing_chain_fields(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)

    with pytest.raises(FallbackWriterContract, match="missing chain field"):
        writer.append({"event_id": "evt-1", "row_id": 1, "prev_hash": "x"})  # missing current_hash
    writer.release_lock()


def test_append_rejects_event_with_prompt_field(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)

    with pytest.raises(FallbackWriterContract, match="forbidden raw text field"):
        writer.append({**_event(), "prompt": "secret"})
    writer.release_lock()


def test_list_pending_excludes_replayed_files(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)
    pending = writer.append(_event())
    path = Path(pending["fallback_path"])
    path2 = tmp_path / "audit-fallback-9.jsonl"
    path2.write_text("{}", encoding="utf-8")
    (tmp_path / "audit-fallback-1.jsonl.replayed").write_text("{}", encoding="utf-8")

    listed = writer.list_pending()

    assert path in listed
    assert path2 in listed
    assert all(not p.name.endswith(".replayed") for p in listed)
    writer.release_lock()


def test_replay_iter_yields_events(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)
    path = Path(writer.append(_event())["fallback_path"])

    replayed = list(writer.replay_iter(path))

    assert replayed == [_event()]
    writer.release_lock()


def test_mark_replayed_renames_file(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)
    path = Path(writer.append(_event())["fallback_path"])

    writer.mark_replayed(path)

    assert not path.exists()
    assert Path(str(path) + ".replayed").exists()
    writer.release_lock()


def test_release_lock_removes_lock_file(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)

    writer.release_lock()
    assert not (tmp_path / "fallback.pid").exists()


def test_no_prompt_or_raw_text_in_jsonl_payload(tmp_path: Path) -> None:
    writer = FileFallbackWriter(tmp_path)
    path = Path(writer.append(_event())["fallback_path"])

    payload = path.read_text(encoding="utf-8")
    assert "prompt" not in payload
    assert "raw_text" not in payload
    writer.release_lock()
