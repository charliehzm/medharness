from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "audit-log"))

from clickhouse_writer import (  # noqa: E402
    ClickHouseAuditWriter,
    ClickHouseUnavailable,
    WriterContract,
)
from hashchain import GENESIS_PREV_HASH, compute_hash  # noqa: E402


class FakeClient:
    def __init__(self, query_results: dict[str, list[tuple[object, ...]]] | None = None, insert_raises=None):
        self._query_results = query_results or {}
        self._insert_raises = insert_raises
        self.inserted: list[dict[str, object]] = []

    def query(self, sql: str):
        result = MagicMock()
        result.result_rows = self._query_results.get(sql.strip(), [])
        return result

    def insert(self, table, rows, column_names):
        if self._insert_raises:
            raise self._insert_raises
        self.inserted.append({"table": table, "rows": rows, "columns": column_names})


def _factory(query_results=None, insert_raises=None):
    def factory(**kwargs):
        return FakeClient(query_results=query_results, insert_raises=insert_raises)

    return factory


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
        "context": {"change_id": "feat/T4.3", "step": 6, "data_levels": ["L1"]},
        "result": {"status": "success", "reason": None, "duration_ms": 12.5},
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
    }
    event.update(overrides)
    return event


def test_init_with_empty_table_uses_genesis_and_zero_row_id() -> None:
    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=_factory(
            query_results={
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [],
                "SELECT max(row_id) FROM _audit_log": [],
            }
        ),
    )

    assert writer._last_hash == GENESIS_PREV_HASH
    assert writer._next_row_id == 0


def test_init_with_existing_data_uses_last_hash_and_max_plus_one() -> None:
    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=_factory(
            query_results={
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [("deadbeef",)],
                "SELECT max(row_id) FROM _audit_log": [(41,)],
            }
        ),
    )

    assert writer._last_hash == "deadbeef"
    assert writer._next_row_id == 42


def test_init_fails_when_client_factory_raises() -> None:
    def bad_factory(**kwargs):
        raise RuntimeError("boom")

    with pytest.raises(ClickHouseUnavailable, match="client init failed: boom"):
        ClickHouseAuditWriter(
            host="localhost",
            port=8123,
            user="user",
            password="pass",
            client_factory=bad_factory,
        )


def test_init_fails_when_startup_query_raises() -> None:
    class BrokenClient(FakeClient):
        def query(self, sql: str):
            raise RuntimeError("query boom")

    def factory(**kwargs):
        return BrokenClient()

    with pytest.raises(ClickHouseUnavailable, match="startup query failed: query boom"):
        ClickHouseAuditWriter(
            host="localhost",
            port=8123,
            user="user",
            password="pass",
            client_factory=factory,
        )


def test_append_assigns_row_id_and_advances_chain() -> None:
    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=_factory(
            query_results={
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [],
                "SELECT max(row_id) FROM _audit_log": [],
            }
        ),
    )

    result = writer.append(_event())

    assert result["row_id"] == 0
    assert writer._next_row_id == 1
    assert writer._last_hash == result["current_hash"]


def test_append_returns_correct_envelope() -> None:
    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=_factory(
            query_results={
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [],
                "SELECT max(row_id) FROM _audit_log": [],
            }
        ),
    )

    result = writer.append(_event())
    expected = compute_hash({**_event(), "row_id": 0}, GENESIS_PREV_HASH)

    assert result == {
        "event_id": "evt-0001",
        "row_id": 0,
        "prev_hash": GENESIS_PREV_HASH,
        "current_hash": expected,
    }


def test_append_fails_closed_on_invalid_event_does_not_advance_chain() -> None:
    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=_factory(
            query_results={
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [],
                "SELECT max(row_id) FROM _audit_log": [],
            }
        ),
    )

    with pytest.raises(WriterContract, match="missing required field"):
        writer.append({**_event(), "input_hash": None})  # type: ignore[arg-type]

    assert writer._next_row_id == 0
    assert writer._last_hash == GENESIS_PREV_HASH


def test_append_fails_closed_on_insert_error_does_not_advance_chain() -> None:
    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=_factory(
            query_results={
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [],
                "SELECT max(row_id) FROM _audit_log": [],
            },
            insert_raises=RuntimeError("insert boom"),
        ),
    )

    with pytest.raises(ClickHouseUnavailable, match="insert failed: insert boom"):
        writer.append(_event())

    assert writer._next_row_id == 0
    assert writer._last_hash == GENESIS_PREV_HASH


def test_column_order_matches_t4_1_schema() -> None:
    assert ClickHouseAuditWriter.COLUMN_ORDER == (
        "event_id",
        "timestamp",
        "actor_agent_role",
        "actor_model_id",
        "actor_vendor_family",
        "actor_session_id",
        "action_tool",
        "action_skill",
        "action_operation",
        "context_change_id",
        "context_step",
        "context_data_levels",
        "result_status",
        "result_reason",
        "result_duration_ms",
        "input_hash",
        "output_hash",
        "prev_hash",
        "current_hash",
        "row_id",
    )


def test_insert_payload_contains_no_prompt_field() -> None:
    client = FakeClient(
        query_results={
            "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1": [],
            "SELECT max(row_id) FROM _audit_log": [],
        }
    )

    writer = ClickHouseAuditWriter(
        host="localhost",
        port=8123,
        user="user",
        password="pass",
        client_factory=lambda **kwargs: client,
    )
    writer.append(_event())

    assert len(client.inserted) == 1
    payload = client.inserted[0]
    assert payload["columns"] == ClickHouseAuditWriter.COLUMN_ORDER
    assert "prompt" not in str(payload["rows"])
    assert "raw_text" not in str(payload["rows"])
