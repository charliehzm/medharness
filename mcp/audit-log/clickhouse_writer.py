from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hashchain import GENESIS_PREV_HASH, compute_hash


class ClickHouseUnavailable(Exception):
    """Raised when ClickHouse client init or query fails."""


class WriterContract(Exception):
    """Raised when a caller passes an invalid audit event payload."""


class ClickHouseAuditWriter:
    """Append-only audit log writer with writer-side row_id and hash chain."""

    COLUMN_ORDER = (
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

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str = "default",
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._database = database
        self._client = self._init_client(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            client_factory=client_factory,
        )
        self._last_hash = self._fetch_last_hash()
        self._next_row_id = self._fetch_max_row_id() + 1

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        from clickhouse_connect import get_client

        return get_client(**kwargs)

    def _init_client(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        client_factory: Callable[..., Any] | None,
    ) -> Any:
        factory = client_factory or self._default_client_factory
        try:
            return factory(host=host, port=port, user=user, password=password, database=database)
        except Exception as exc:  # pragma: no cover - exercised through tests
            raise ClickHouseUnavailable(f"client init failed: {exc}") from exc

    def _fetch_last_hash(self) -> str:
        try:
            result = self._client.query("SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1")
        except Exception as exc:
            raise ClickHouseUnavailable(f"startup query failed: {exc}") from exc
        if getattr(result, "result_rows", None):
            return result.result_rows[0][0]
        return GENESIS_PREV_HASH

    def _fetch_max_row_id(self) -> int:
        try:
            result = self._client.query("SELECT max(row_id) FROM _audit_log")
        except Exception as exc:
            raise ClickHouseUnavailable(f"startup query failed: {exc}") from exc
        if getattr(result, "result_rows", None):
            max_row_id = result.result_rows[0][0]
            if max_row_id is not None:
                return int(max_row_id)
        return -1

    @staticmethod
    def _required_event_fields(event: dict[str, Any]) -> tuple[str, ...]:
        return ("event_id", "timestamp", "actor", "action", "context", "result", "input_hash", "output_hash")

    @staticmethod
    def _validate_event(event: dict[str, Any]) -> None:
        missing = [
            field
            for field in ClickHouseAuditWriter._required_event_fields(event)
            if field not in event or event[field] in (None, "")
        ]
        if missing:
            joined = ", ".join(missing)
            raise WriterContract(f"event missing required field(s): {joined}")
        if "prompt" in event or "raw_text" in event:
            raise WriterContract("event contains forbidden raw text field")

    @staticmethod
    def _build_row(event: dict[str, Any], prev_hash: str, current_hash: str) -> tuple[Any, ...]:
        actor = event["actor"]
        action = event["action"]
        context = event["context"]
        result = event["result"]
        return (
            event["event_id"],
            event["timestamp"],
            actor.get("agent_role", ""),
            actor.get("model_id", ""),
            actor.get("vendor_family", ""),
            actor.get("session_id", ""),
            action.get("tool", ""),
            action.get("skill"),
            action.get("operation", ""),
            context.get("change_id"),
            context.get("step"),
            context.get("data_levels", []),
            result.get("status", ""),
            result.get("reason"),
            result.get("duration_ms", 0.0),
            event["input_hash"],
            event["output_hash"],
            prev_hash,
            current_hash,
            event["row_id"],
        )

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        self._validate_event(event)
        row_id = self._next_row_id
        event_with_row_id = dict(event)
        event_with_row_id["row_id"] = row_id

        prev_hash = self._last_hash
        try:
            current_hash = compute_hash(event_with_row_id, prev_hash)
        except ValueError as exc:
            raise WriterContract(f"event invalid: {exc}") from exc

        row = self._build_row(event_with_row_id, prev_hash, current_hash)

        try:
            self._client.insert("_audit_log", [row], column_names=self.COLUMN_ORDER)
        except Exception as exc:  # pragma: no cover - exercised through tests
            raise ClickHouseUnavailable(f"insert failed: {exc}") from exc

        self._last_hash = current_hash
        self._next_row_id += 1
        return {
            "event_id": event["event_id"],
            "row_id": row_id,
            "prev_hash": prev_hash,
            "current_hash": current_hash,
        }
