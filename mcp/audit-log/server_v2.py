from __future__ import annotations

import enum
import logging
from pathlib import Path
from typing import Any

from clickhouse_writer import ClickHouseAuditWriter, ClickHouseUnavailable, WriterContract
from fallback_writer import FallbackLockHeld, FallbackWriterContract, FileFallbackWriter
from hashchain import GENESIS_PREV_HASH, compute_hash

LOGGER = logging.getLogger(__name__)


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

        try:
            self._ch_writer = self._clickhouse_writer_factory(**self._clickhouse_config)
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
            new_ch = self._clickhouse_writer_factory(**self._clickhouse_config)
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

    def query(self, sql: str) -> list[dict[str, Any]]:
        if self._state != ServerState.NORMAL or self._ch_writer is None:
            return []
        try:
            result = self._ch_writer._client.query(sql)
        except Exception as exc:
            LOGGER.error("query failed: %s", exc)
            return []
        return [{"row": row} for row in getattr(result, "result_rows", [])]

    def verify(self) -> dict[str, Any]:
        return {"status": "not_implemented", "message": "use scripts/verify-hashchain.sh (T4.7)"}

    def seal_bundle(self) -> dict[str, Any]:
        return {
            "status": "placeholder",
            "chain_head": self._last_hash,
            "next_row_id": self._next_row_id,
        }
