from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_DIR = ROOT / "mcp" / "audit-log"
SERVER = AUDIT_LOG_DIR / "server_v2.py"


def _load_module(module_name: str, path: Path, alias: str | None = None):
    spec = util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    if alias is not None:
        sys.modules[alias] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


hashchain_mod = _load_module(
    "audit_log_hashchain", AUDIT_LOG_DIR / "hashchain.py", alias="hashchain"
)
clickhouse_writer_mod = _load_module(
    "audit_log_clickhouse_writer", AUDIT_LOG_DIR / "clickhouse_writer.py", alias="clickhouse_writer"
)
fallback_writer_mod = _load_module(
    "audit_log_fallback_writer", AUDIT_LOG_DIR / "fallback_writer.py", alias="fallback_writer"
)
audit_server_v2 = _load_module("audit_log_server_v2", SERVER)

ClickHouseAuditWriter = clickhouse_writer_mod.ClickHouseAuditWriter
ClickHouseUnavailable = clickhouse_writer_mod.ClickHouseUnavailable
WriterContract = clickhouse_writer_mod.WriterContract
GENESIS_PREV_HASH = hashchain_mod.GENESIS_PREV_HASH
compute_hash = hashchain_mod.compute_hash
AuditLogServerV2 = audit_server_v2.AuditLogServerV2
AuditServerError = audit_server_v2.AuditServerError
ServerState = audit_server_v2.ServerState


class FakeClickHouseWriter:
    def __init__(self, last_hash="GENESIS", next_row_id=0, append_raises=None, init_raises=None):
        if init_raises:
            raise init_raises
        self._last_hash = last_hash
        self._next_row_id = next_row_id
        self.appended: list[dict[str, object]] = []
        self._append_raises = append_raises
        self._client = MagicMock()
        self._client.inserted = []
        self._client.insert.side_effect = self._record_insert
        self.COLUMN_ORDER = ClickHouseAuditWriter.COLUMN_ORDER
        self._build_row = ClickHouseAuditWriter._build_row
        self._fetch_last_hash = lambda: self._last_hash
        self._fetch_max_row_id = lambda: self._next_row_id - 1

    def _record_insert(self, table, rows, column_names):
        self._client.inserted.append({"table": table, "rows": rows, "columns": column_names})

    def append(self, event):
        if self._append_raises:
            raise self._append_raises
        event_with_row_id = {**event, "row_id": self._next_row_id}
        current_hash = compute_hash(event_with_row_id, self._last_hash)
        result = {
            "event_id": event["event_id"],
            "row_id": self._next_row_id,
            "prev_hash": self._last_hash,
            "current_hash": current_hash,
        }
        self.appended.append(event_with_row_id)
        self._last_hash = current_hash
        self._next_row_id += 1
        return result


class FakeFallbackWriter:
    def __init__(self, base_dir):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._pending: list[Path] = []
        self.appended: list[dict[str, object]] = []

    def append(self, event_with_hash):
        self.appended.append(event_with_hash)
        path = self._base_dir / "audit-fallback-1.jsonl"
        line = json.dumps(event_with_hash, ensure_ascii=False, sort_keys=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._pending = [path]
        return {
            "event_id": event_with_hash["event_id"],
            "row_id": event_with_hash["row_id"],
            "prev_hash": event_with_hash["prev_hash"],
            "current_hash": event_with_hash["current_hash"],
            "fallback_path": str(path),
        }

    def list_pending(self):
        return [p for p in self._pending if p.exists()]

    def replay_iter(self, path):
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)

    def mark_replayed(self, path):
        path.rename(path.with_name(path.name + ".replayed"))
        self._pending = []


def _event(**overrides):
    event = {
        "event_id": "evt-0001",
        "timestamp": "2026-05-24T03:00:00.000Z",
        "actor": {
            "agent_role": "coder",
            "model_id": "qwen-max",
            "vendor_family": "alibaba",
            "session_id": "session-1",
        },
        "action": {"tool": "shell", "skill": None, "operation": "write"},
        "context": {"change_id": "feat/T4.5", "step": 6, "data_levels": ["L1"]},
        "result": {"status": "success", "reason": None, "duration_ms": 12.5},
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
    }
    event.update(overrides)
    return event


def _server(
    *,
    fallback_base_dir: Path,
    ch_init_raises=None,
    ch_append_raises=None,
    ch_last_hash=GENESIS_PREV_HASH,
    ch_next_row_id=0,
    fb_writer_factory=None,
) -> AuditLogServerV2:
    init_failures = {"count": 0}

    def ch_factory(**kwargs):
        if init_failures["count"] == 0:
            init_failures["count"] += 1
            init_raises = ch_init_raises
        else:
            init_raises = None
        return FakeClickHouseWriter(
            last_hash=ch_last_hash,
            next_row_id=ch_next_row_id,
            append_raises=ch_append_raises,
            init_raises=init_raises,
        )

    def fb_factory(base_dir):
        return (fb_writer_factory or FakeFallbackWriter)(base_dir)

    return AuditLogServerV2(
        clickhouse_config={"host": "localhost", "port": 8123, "user": "user", "password": "pass"},
        fallback_base_dir=fallback_base_dir,
        clickhouse_writer_factory=ch_factory,
        fallback_writer_factory=fb_factory,
    )


def test_init_with_clickhouse_available_enters_normal(tmp_path: Path) -> None:
    server = AuditLogServerV2(
        clickhouse_config={"host": "localhost", "port": 8123, "user": "user", "password": "pass"},
        fallback_base_dir=tmp_path,
        clickhouse_writer_factory=lambda **kwargs: FakeClickHouseWriter(
            last_hash="hash-1", next_row_id=3
        ),
        fallback_writer_factory=lambda base_dir: FakeFallbackWriter(base_dir),
    )

    assert server._state == ServerState.NORMAL
    assert server._last_hash == "hash-1"
    assert server._next_row_id == 3


def test_init_with_clickhouse_unavailable_enters_fallback(tmp_path: Path) -> None:
    server = AuditLogServerV2(
        clickhouse_config={"host": "localhost", "port": 8123, "user": "user", "password": "pass"},
        fallback_base_dir=tmp_path,
        clickhouse_writer_factory=lambda **kwargs: (_ for _ in ()).throw(
            ClickHouseUnavailable("boom")
        ),
        fallback_writer_factory=lambda base_dir: FakeFallbackWriter(base_dir),
    )

    assert server._state == ServerState.FALLBACK
    assert server._last_hash == GENESIS_PREV_HASH


def test_append_in_normal_uses_clickhouse_writer(tmp_path: Path) -> None:
    server = AuditLogServerV2(
        clickhouse_config={"host": "localhost", "port": 8123, "user": "user", "password": "pass"},
        fallback_base_dir=tmp_path,
        clickhouse_writer_factory=lambda **kwargs: FakeClickHouseWriter(),
        fallback_writer_factory=lambda base_dir: FakeFallbackWriter(base_dir),
    )

    result = server.append(_event())

    assert result["state"] == "normal"
    assert result["row_id"] == 0


def test_append_clickhouse_failure_switches_to_fallback_and_completes(tmp_path: Path) -> None:
    server = AuditLogServerV2(
        clickhouse_config={"host": "localhost", "port": 8123, "user": "user", "password": "pass"},
        fallback_base_dir=tmp_path,
        clickhouse_writer_factory=lambda **kwargs: FakeClickHouseWriter(
            append_raises=ClickHouseUnavailable("insert boom")
        ),
        fallback_writer_factory=lambda base_dir: FakeFallbackWriter(base_dir),
    )

    result = server.append(_event())

    assert result["state"] == "fallback"
    assert "fallback_path" in result
    assert server._state == ServerState.FALLBACK


def test_append_in_fallback_computes_hash_and_uses_fb_writer(tmp_path: Path) -> None:
    server = _server(
        fallback_base_dir=tmp_path,
        ch_init_raises=ClickHouseUnavailable("boom"),
    )
    result = server.append(_event())

    assert result["state"] == "fallback"
    assert result["prev_hash"] == GENESIS_PREV_HASH
    assert result["row_id"] == 0


def test_append_writer_contract_propagates_in_any_state(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path, ch_init_raises=ClickHouseUnavailable("boom"))

    with pytest.raises(WriterContract):
        server.append({**_event(), "input_hash": None})  # type: ignore[arg-type]


def test_append_in_backfill_raises_audit_server_error(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path, ch_init_raises=ClickHouseUnavailable("boom"))
    server._state = ServerState.BACKFILL

    with pytest.raises(AuditServerError, match="writes paused"):
        server.append(_event())


def test_recover_replays_pending_and_returns_to_normal(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path, ch_init_raises=ClickHouseUnavailable("boom"))
    server.append(_event())
    server.append(_event(event_id="evt-2"))
    result = server.recover()

    assert result["final_state"] == "normal"
    assert result["replayed_files"] == 1
    assert result["replayed_events"] == 2


def test_recover_failure_keeps_state_in_fallback(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path, ch_init_raises=ClickHouseUnavailable("boom"))
    server.append(_event())
    first = server.recover()
    assert first["final_state"] == "normal"
    server._state = ServerState.FALLBACK
    server._clickhouse_writer_factory = lambda **kwargs: (_ for _ in ()).throw(
        ClickHouseUnavailable("still down")
    )

    result = server.recover()

    assert result["final_state"] == "fallback"
    assert "error" in result
    assert server._state == ServerState.FALLBACK


def test_recover_skip_when_already_normal(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path)

    result = server.recover()

    assert result["skipped"] is True
    assert result["final_state"] == "normal"


def test_recover_idempotent_mark_replayed_safe_to_rerun(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path, ch_init_raises=ClickHouseUnavailable("boom"))
    server.append(_event())
    first = server.recover()
    second = server.recover()

    assert first["final_state"] == "normal"
    assert second["skipped"] is True
    assert second["final_state"] == "normal"


def test_health_returns_current_state_and_chain_head(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path)

    health = server.health()

    assert health["state"] == "normal"
    assert "last_hash" in health
    assert "next_row_id" in health


def test_no_prompt_field_in_any_state_output(tmp_path: Path) -> None:
    server = _server(fallback_base_dir=tmp_path, ch_init_raises=ClickHouseUnavailable("boom"))
    result = server.append(_event())
    health = server.health()

    result_without_path = {k: v for k, v in result.items() if k != "fallback_path"}
    assert "prompt" not in json.dumps(result_without_path, ensure_ascii=False)
    assert "prompt" not in json.dumps(health, ensure_ascii=False)


def test_chain_head_continuity_across_normal_to_fallback_transition(tmp_path: Path) -> None:
    server = AuditLogServerV2(
        clickhouse_config={"host": "localhost", "port": 8123, "user": "user", "password": "pass"},
        fallback_base_dir=tmp_path,
        clickhouse_writer_factory=lambda **kwargs: FakeClickHouseWriter(
            append_raises=ClickHouseUnavailable("insert boom")
        ),
        fallback_writer_factory=lambda base_dir: FakeFallbackWriter(base_dir),
    )

    result = server.append(_event())

    assert result["prev_hash"] == GENESIS_PREV_HASH
    assert server._last_hash == result["current_hash"]
