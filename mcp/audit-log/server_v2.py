from __future__ import annotations

import enum
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from clickhouse_writer import ClickHouseAuditWriter, ClickHouseUnavailable, WriterContract
from fallback_writer import FallbackLockHeld, FallbackWriterContract, FileFallbackWriter
from hashchain import GENESIS_PREV_HASH, compute_hash, verify_chain

LOGGER = logging.getLogger(__name__)
DEFAULT_FALLBACK_DIR = Path("/data/medharness/audit")
DEFAULT_SCHEMA_PATH = Path(__file__).with_name("sql") / "audit_log.sql"


class ServerState(enum.Enum):
    NORMAL = "normal"
    FALLBACK = "fallback"
    BACKFILL = "backfill"


class AuditServerError(Exception):
    """Top-level server error."""


class AuditLogServerV2:
    """Audit log server with NORMAL / FALLBACK / BACKFILL state machine."""

    def __init__(
        self,
        clickhouse_config: dict[str, Any],
        fallback_base_dir: Path,
        clickhouse_writer_factory=None,
        fallback_writer_factory=None,
    ) -> None:
        self._clickhouse_config = dict(clickhouse_config)
        self._fallback_base_dir = Path(fallback_base_dir)
        self._clickhouse_writer_factory = clickhouse_writer_factory or self._default_ch_factory
        self._fallback_writer_factory = fallback_writer_factory or self._default_fb_factory
        self._state = ServerState.NORMAL
        self._ch_writer: ClickHouseAuditWriter | None = None
        self._fb_writer: FileFallbackWriter | None = None
        self._last_hash = GENESIS_PREV_HASH
        self._next_row_id = 0
        self._schema_sql: str | None = None

        try:
            self._schema_sql = self._load_schema(DEFAULT_SCHEMA_PATH)
            self._ch_writer = self._clickhouse_writer_factory(
                **self._clickhouse_config,
                schema_sql=self._schema_sql,
            )
            self._last_hash = self._ch_writer._last_hash
            self._next_row_id = self._ch_writer._next_row_id
            self._state = ServerState.NORMAL
        except ClickHouseUnavailable as exc:
            LOGGER.warning("ClickHouse unavailable at startup, entering FALLBACK: %s", exc)
            self._enter_fallback()

    @staticmethod
    def _default_ch_factory(**kwargs: Any) -> ClickHouseAuditWriter:
        return ClickHouseAuditWriter(**kwargs)

    @staticmethod
    def _default_fb_factory(base_dir: Path) -> FileFallbackWriter:
        return FileFallbackWriter(base_dir)

    def _enter_fallback(self) -> None:
        if self._fb_writer is None:
            self._fb_writer = self._fallback_writer_factory(self._fallback_base_dir)
        self._state = ServerState.FALLBACK

    @staticmethod
    def _server_event_with_row_id(event: dict[str, Any], row_id: int) -> dict[str, Any]:
        return {**event, "row_id": row_id}

    @staticmethod
    def _validate_event(event: dict[str, Any]) -> None:
        ClickHouseAuditWriter._validate_event(event)

    @staticmethod
    def _load_schema(schema_path: Path = DEFAULT_SCHEMA_PATH) -> str:
        return schema_path.read_text(encoding="utf-8")

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        if self._state == ServerState.BACKFILL:
            raise AuditServerError("server is in BACKFILL state; writes paused")

        self._validate_event(event)

        if self._state == ServerState.NORMAL and self._ch_writer is not None:
            try:
                result = self._ch_writer.append(event)
            except WriterContract:
                raise
            except ClickHouseUnavailable as exc:
                LOGGER.warning("ClickHouse failed during append, switching to FALLBACK: %s", exc)
                self._enter_fallback()
            else:
                self._last_hash = result["current_hash"]
                self._next_row_id = result["row_id"] + 1
                return {**result, "state": self._state.value}

        if self._state == ServerState.FALLBACK:
            if self._fb_writer is None:
                self._enter_fallback()
            row_id = self._next_row_id
            event_with_row_id = self._server_event_with_row_id(event, row_id)
            try:
                current_hash = compute_hash(event_with_row_id, self._last_hash)
            except ValueError as exc:
                raise WriterContract(f"event invalid: {exc}") from exc

            event_full = {
                **event_with_row_id,
                "prev_hash": self._last_hash,
                "current_hash": current_hash,
            }
            try:
                result = self._fb_writer.append(event_full)
            except FallbackWriterContract:
                raise
            except FallbackLockHeld as exc:
                raise AuditServerError(f"fallback writer unavailable: {exc}") from exc
            except Exception as exc:  # pragma: no cover - fallback safety net
                raise AuditServerError(f"fallback writer failed: {exc}") from exc

            self._last_hash = current_hash
            self._next_row_id += 1
            return {
                "event_id": result["event_id"],
                "row_id": result["row_id"],
                "prev_hash": result["prev_hash"],
                "current_hash": result["current_hash"],
                "state": self._state.value,
                "fallback_path": result["fallback_path"],
            }

        raise AuditServerError(f"unexpected state: {self._state}")

    def recover(self) -> dict[str, Any]:
        if self._state == ServerState.NORMAL:
            return {
                "replayed_files": 0,
                "replayed_events": 0,
                "final_state": self._state.value,
                "skipped": True,
            }
        if self._state != ServerState.FALLBACK:
            return {
                "replayed_files": 0,
                "replayed_events": 0,
                "final_state": self._state.value,
                "skipped": True,
            }

        if self._fb_writer is None:
            return {
                "replayed_files": 0,
                "replayed_events": 0,
                "final_state": self._state.value,
                "error": "fallback writer unavailable",
            }

        try:
            new_ch = self._clickhouse_writer_factory(
                **self._clickhouse_config,
                schema_sql=self._schema_sql or self._load_schema(DEFAULT_SCHEMA_PATH),
            )
        except ClickHouseUnavailable as exc:
            LOGGER.warning("ClickHouse still unavailable in recover(): %s", exc)
            return {
                "replayed_files": 0,
                "replayed_events": 0,
                "final_state": self._state.value,
                "error": str(exc),
            }

        self._state = ServerState.BACKFILL
        replayed_files = 0
        replayed_events = 0

        pending = self._fb_writer.list_pending()
        for path in pending:
            for event in self._fb_writer.replay_iter(path):
                row = new_ch._build_row(event, event["prev_hash"], event["current_hash"])
                try:
                    new_ch._client.insert("_audit_log", [row], column_names=new_ch.COLUMN_ORDER)
                except Exception as exc:
                    LOGGER.error(
                        "backfill insert failed for row_id=%s: %s", event.get("row_id"), exc
                    )
                    return {
                        "replayed_files": replayed_files,
                        "replayed_events": replayed_events,
                        "final_state": self._state.value,
                        "error": str(exc),
                    }
                new_ch._last_hash = event["current_hash"]
                new_ch._next_row_id = int(event["row_id"]) + 1
                replayed_events += 1
            replayed_path = path.with_name(path.name + ".replayed")
            if not replayed_path.exists():
                self._fb_writer.mark_replayed(path)
            replayed_files += 1

        self._ch_writer = new_ch
        self._last_hash = new_ch._fetch_last_hash()
        self._next_row_id = new_ch._fetch_max_row_id() + 1
        self._state = ServerState.NORMAL
        return {
            "replayed_files": replayed_files,
            "replayed_events": replayed_events,
            "final_state": self._state.value,
        }

    def health(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "last_hash": self._last_hash,
            "next_row_id": self._next_row_id,
            "ch_available": self._ch_writer is not None,
            "fb_available": self._fb_writer is not None,
        }

    def query(self, sql: str) -> dict[str, Any]:
        # M1: surface the audit backend state so a degraded backend is never silently
        # rendered as "no data". Callers (A0 /audit, /posture) MUST show `degraded`
        # explicitly rather than treating an empty list as a healthy empty result.
        if self._state != ServerState.NORMAL or self._ch_writer is None:
            return {"degraded": True, "state": self._state.value, "rows": []}
        try:
            result = self._ch_writer._client.query(sql)
        except Exception as exc:
            LOGGER.error("query failed: %s", exc)
            return {
                "degraded": True,
                "state": self._state.value,
                "error": "query_unavailable",
                "rows": [],
            }
        return {
            "degraded": False,
            "state": self._state.value,
            "rows": [{"row": row} for row in getattr(result, "result_rows", [])],
        }

    def seal_bundle(self) -> dict[str, Any]:
        return {
            "status": "placeholder",
            "chain_head": self._last_hash,
            "next_row_id": self._next_row_id,
        }

    def verify(self, limit: int | None = None) -> dict[str, Any]:
        if self._state != ServerState.NORMAL or self._ch_writer is None:
            return {
                "degraded": True,
                "state": self._state.value,
                "status": "skipped",
                "passed": False,
                "row_count": 0,
                "broken_at_row_id": None,
            }
        try:
            rows = self._ch_writer.fetch_chain_rows(limit=limit)
        except ClickHouseUnavailable:
            return {
                "degraded": True,
                "state": self._state.value,
                "status": "unavailable",
                "passed": False,
                "row_count": 0,
                "broken_at_row_id": None,
            }
        ok, broken_at = verify_chain(rows)
        return {
            "degraded": False,
            "state": self._state.value,
            "status": "ok" if ok else "tampered",
            "passed": ok,
            "row_count": len(rows),
            "broken_at_row_id": broken_at,
        }


def _config_from_env() -> dict[str, Any]:
    return {
        "host": os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
        "port": int(os.environ.get("CLICKHOUSE_HTTP_PORT", "8123")),
        "user": os.environ.get("CLICKHOUSE_USER", "medharness"),
        "password": os.environ.get("CLICKHOUSE_PASSWORD", ""),
        "database": os.environ.get("CLICKHOUSE_DATABASE", "medharness"),
    }


def _fallback_dir_from_env() -> Path:
    return Path(os.environ.get("MEDHARNESS_AUDIT_FALLBACK_DIR", str(DEFAULT_FALLBACK_DIR)))


def _server_from_env() -> AuditLogServerV2:
    return AuditLogServerV2(
        clickhouse_config=_config_from_env(),
        fallback_base_dir=_fallback_dir_from_env(),
    )


def _ensure_schema(
    server: AuditLogServerV2, schema_path: Path = DEFAULT_SCHEMA_PATH
) -> dict[str, Any]:
    schema_sql = server._load_schema(schema_path)
    if server._ch_writer is None:
        server._schema_sql = schema_sql
        server._ch_writer = server._clickhouse_writer_factory(
            **server._clickhouse_config,
            schema_sql=schema_sql,
        )
        server._last_hash = server._ch_writer._last_hash
        server._next_row_id = server._ch_writer._next_row_id
        server._state = ServerState.NORMAL
        return {"status": "ok", "state": server._state.value, "degraded": False}
    server._ch_writer.ensure_schema(schema_sql)
    return {"status": "ok", "state": server._state.value, "degraded": False}


def _response_for_request(server: AuditLogServerV2, req: dict[str, Any]) -> dict[str, Any]:
    method = req.get("method")
    params = req.get("params", {})
    if not isinstance(params, dict):
        params = {}
    try:
        if method == "append":
            result = server.append(params)
        elif method == "query":
            sql = str(params.get("sql", "SELECT * FROM _audit_log ORDER BY row_id DESC LIMIT 100"))
            result = server.query(sql)
        elif method == "verify":
            limit = params.get("limit")
            result = server.verify(limit=int(limit) if limit is not None else None)
        elif method == "recover":
            result = server.recover()
        elif method == "seal_bundle":
            result = server.seal_bundle()
        elif method == "health":
            result = server.health()
        elif method == "ensure_schema":
            result = _ensure_schema(server)
        else:
            return {
                "id": req.get("id"),
                "error": {"code": "method_not_found", "msg": "unsupported audit-log method"},
            }
        return {"id": req.get("id"), "result": result}
    except (AuditServerError, ClickHouseUnavailable, WriterContract, FallbackWriterContract):
        return {
            "id": req.get("id"),
            "error": {"code": "audit_log_unavailable", "msg": "audit-log request failed"},
        }


def _serve_stdio(server: AuditLogServerV2) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _response_for_request(server, req if isinstance(req, dict) else {})
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    server = _server_from_env()
    if cmd == "serve" and len(sys.argv) >= 3 and sys.argv[2] == "--stdio":
        return _serve_stdio(server)
    if cmd == "health":
        print(json.dumps(server.health(), ensure_ascii=False, sort_keys=True))
        return 0
    if cmd == "ensure-schema":
        result = _ensure_schema(server)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "ok" else 1
    if cmd == "verify":
        result = server.verify()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["passed"] else 1
    if cmd == "recover":
        print(json.dumps(server.recover(), ensure_ascii=False, sort_keys=True))
        return 0
    print(
        json.dumps(
            {"error": {"code": "unknown_command", "msg": "unsupported audit-log command"}},
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
