from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib import error, parse, request

from hashchain import GENESIS_PREV_HASH, compute_hash


class ClickHouseUnavailable(Exception):
    """Raised when ClickHouse client init or query fails."""


class WriterContract(Exception):
    """Raised when a caller passes an invalid audit event payload."""


class _ClickHouseHttpResult:
    def __init__(self, result_rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = result_rows


class _ClickHouseHttpClient:
    """Tiny ClickHouse HTTP client using only Python stdlib.

    The audit-log container intentionally keeps a small dependency surface. This
    adapter implements the three methods the writer needs from ClickHouse:
    ``command``, ``query`` and ``insert``.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        timeout: float = 5.0,
    ) -> None:
        self._url = f"http://{host}:{int(port)}/?{parse.urlencode({'database': database})}"
        self._auth_header = self._basic_auth(user, password)
        self._timeout = timeout

    @staticmethod
    def _basic_auth(user: str, password: str) -> str:
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        return f"Basic {token}"

    @staticmethod
    def _has_format(sql: str) -> bool:
        return " FORMAT " in f" {sql.upper()} "

    def _post(self, sql: str) -> str:
        req = request.Request(
            self._url,
            data=sql.encode("utf-8"),
            method="POST",
            headers={"Authorization": self._auth_header},
        )
        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                return resp.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:240]
            raise ClickHouseUnavailable(f"HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise ClickHouseUnavailable(f"HTTP request failed: {exc}") from exc

    def command(self, sql: str) -> None:
        self._post(sql)

    def query(self, sql: str) -> _ClickHouseHttpResult:
        query_sql = sql if self._has_format(sql) else f"{sql} FORMAT JSONCompact"
        payload = self._post(query_sql)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ClickHouseUnavailable("query response was not JSON") from exc

        data = parsed.get("data", [])
        if not isinstance(data, list):
            raise ClickHouseUnavailable("query response data was invalid")
        rows = [tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in data]
        return _ClickHouseHttpResult(rows)

    def insert(
        self, table: str, rows: list[tuple[Any, ...]], column_names: tuple[str, ...]
    ) -> None:
        columns = ", ".join(column_names)
        sql_prefix = f"INSERT INTO {table} ({columns}) FORMAT JSONEachRow"
        payload = "\n".join(
            json.dumps(dict(zip(column_names, row, strict=True)), ensure_ascii=False)
            for row in rows
        )
        self._post(f"{sql_prefix}\n{payload}")


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
        schema_sql: str | None = None,
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
        if schema_sql is not None:
            self.ensure_schema(schema_sql)
        self._last_hash = self._fetch_last_hash()
        self._next_row_id = self._fetch_max_row_id() + 1

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        return _ClickHouseHttpClient(**kwargs)

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

    def ensure_schema(self, sql: str) -> None:
        """Create the ClickHouse audit table when the deployment has not bootstrapped it."""

        statements = [
            self._idempotent_schema_statement(statement.strip())
            for statement in sql.split(";")
            if statement.strip() and not statement.lstrip().upper().startswith(("GRANT", "REVOKE"))
        ]
        try:
            for statement in statements:
                self._client.command(statement)
        except Exception as exc:  # pragma: no cover - exercised through tests
            raise ClickHouseUnavailable(f"schema init failed: {exc}") from exc

    @staticmethod
    def _idempotent_schema_statement(statement: str) -> str:
        upper = statement.upper()
        marker = "CREATE TABLE "
        if marker in upper and "CREATE TABLE IF NOT EXISTS " not in upper:
            index = upper.index(marker)
            return (
                f"{statement[:index]}CREATE TABLE IF NOT EXISTS "
                f"{statement[index + len(marker):]}"
            )
        return statement

    def _fetch_last_hash(self) -> str:
        try:
            result = self._client.query(
                "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1"
            )
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
        return (
            "event_id",
            "timestamp",
            "actor",
            "action",
            "context",
            "result",
            "input_hash",
            "output_hash",
        )

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

    @staticmethod
    def _iso_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return str(value)

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> dict[str, Any]:
        data = dict(zip(ClickHouseAuditWriter.COLUMN_ORDER, row, strict=True))
        return {
            "event_id": str(data["event_id"]),
            "timestamp": ClickHouseAuditWriter._iso_timestamp(data["timestamp"]),
            "actor": {
                "agent_role": data["actor_agent_role"],
                "model_id": data["actor_model_id"],
                "vendor_family": data["actor_vendor_family"],
                "session_id": data["actor_session_id"],
            },
            "action": {
                "tool": data["action_tool"],
                "skill": data["action_skill"],
                "operation": data["action_operation"],
            },
            "context": {
                "change_id": data["context_change_id"],
                "step": data["context_step"],
                "data_levels": list(data["context_data_levels"] or []),
            },
            "result": {
                "status": data["result_status"],
                "reason": data["result_reason"],
                "duration_ms": float(data["result_duration_ms"]),
            },
            "input_hash": data["input_hash"],
            "output_hash": data["output_hash"],
            "row_id": int(data["row_id"]),
            "prev_hash": data["prev_hash"],
            "current_hash": data["current_hash"],
        }

    def fetch_chain_rows(self, limit: int | None = None) -> list[dict[str, Any]]:
        sql = f"SELECT {', '.join(self.COLUMN_ORDER)} FROM _audit_log ORDER BY row_id ASC"
        if limit is not None:
            sql = f"{sql} LIMIT {int(limit)}"
        try:
            result = self._client.query(sql)
        except Exception as exc:  # pragma: no cover - exercised through tests
            raise ClickHouseUnavailable(f"verify query failed: {exc}") from exc
        return [self._row_to_event(row) for row in getattr(result, "result_rows", [])]

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
