#!/usr/bin/env python3
"""mcp-desensitize v2 · AES-GCM envelope integration."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

sys.path.insert(0, str(Path(__file__).parent))

from crypto_envelope import decrypt_mapping, encrypt_mapping  # noqa: E402
from key_provider import (  # noqa: E402
    ChangeId,
    EncryptedEnvelopeMetadata,
    EncryptionContext,
    KeyId,
    KeyNotFoundError,
    KeyProviderError,
    MapId,
)
from key_provider.file_provider import FileKeyProvider  # noqa: E402
from server import SUBSTITUTIONS  # noqa: E402

DEFAULT_KEY_ID = "active"
DEFAULT_REVERSE_TOKEN_ENV = "COMPLIANCE_REVERSE_TOKEN"
PLACEHOLDER_PREFIX = "PHI"
DEFAULT_CLICKHOUSE_HTTP_PORT = 8123
DEFAULT_CLICKHOUSE_DATABASE = "medharness"
DEFAULT_PHI_LOOKUP_SCHEMA_PATH = Path(__file__).with_name("sql") / "phi_lookup.sql"


class ClickHouseUnavailable(Exception):
    """Raised when ClickHouse client init or query fails."""


def _provider() -> FileKeyProvider:
    return FileKeyProvider.from_env()


def _safe_error(exc: Exception) -> dict[str, str]:
    return {"type": exc.__class__.__name__, "message": str(exc)}


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _load_phi_lookup_schema() -> str:
    return DEFAULT_PHI_LOOKUP_SCHEMA_PATH.read_text(encoding="utf-8")


def _clickhouse_config_from_env() -> dict[str, Any] | None:
    host = os.environ.get("CLICKHOUSE_HOST")
    port = os.environ.get("CLICKHOUSE_HTTP_PORT")
    database = os.environ.get("CLICKHOUSE_DATABASE")
    user = os.environ.get("CLICKHOUSE_USER")
    password = os.environ.get("CLICKHOUSE_PASSWORD")
    required_values = {
        "CLICKHOUSE_HOST": host,
        "CLICKHOUSE_USER": user,
        "CLICKHOUSE_PASSWORD": password,
    }
    if not any(value is not None and str(value).strip() for value in required_values.values()):
        return None
    missing = [
        name for name, value in required_values.items() if not value or not str(value).strip()
    ]
    if missing:
        joined = ", ".join(missing)
        raise ClickHouseUnavailable(f"clickhouse configuration incomplete: {joined}")
    try:
        port_value = int(str(port or DEFAULT_CLICKHOUSE_HTTP_PORT))
    except ValueError as exc:
        raise ClickHouseUnavailable("invalid clickhouse HTTP port") from exc
    return {
        "host": str(host),
        "port": port_value,
        "user": str(user),
        "password": str(password),
        "database": str(database or DEFAULT_CLICKHOUSE_DATABASE),
    }


def _request_map_id(request_payload: dict[str, Any]) -> str | None:
    context = request_payload.get("context")
    if isinstance(context, dict):
        map_id = context.get("map_id")
        if map_id not in (None, ""):
            return str(map_id)
    map_id = request_payload.get("map_id")
    if map_id not in (None, ""):
        return str(map_id)
    return None


def _phi_lookup_row_values(
    context: EncryptionContext,
    metadata: EncryptedEnvelopeMetadata,
    ciphertext_b64: str,
    key_generation: int,
    *,
    now: datetime | None = None,
) -> tuple[Any, ...]:
    current = now or datetime.now(timezone.utc)
    ciphertext = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
    retention_until = current + timedelta(days=365 * 6)
    return (
        str(context.map_id),
        str(context.change_id),
        str(context.key_id),
        int(key_generation),
        metadata.algorithm,
        metadata.schema_version,
        metadata.nonce_b64,
        metadata.aad_sha256,
        ciphertext_b64,
        hashlib.sha256(ciphertext).hexdigest(),
        _iso_timestamp(current),
        _iso_timestamp(retention_until),
        _iso_timestamp(current),
    )


class _ClickHouseHttpResult:
    def __init__(self, result_rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = result_rows


class _ClickHouseHttpClient:
    """Tiny ClickHouse HTTP client using only Python stdlib."""

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


class ClickHousePhiLookupStore:
    COLUMN_ORDER = (
        "map_id",
        "change_id",
        "key_id",
        "key_generation",
        "algorithm",
        "schema_version",
        "nonce_b64",
        "aad_sha256",
        "ciphertext_b64",
        "ciphertext_sha256",
        "created_at",
        "retention_until",
        "inserted_at",
    )

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str = DEFAULT_CLICKHOUSE_DATABASE,
        client_factory: Any | None = None,
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
        client_factory: Any | None,
    ) -> Any:
        factory = client_factory or self._default_client_factory
        try:
            return factory(host=host, port=port, user=user, password=password, database=database)
        except Exception as exc:
            raise ClickHouseUnavailable(f"client init failed: {exc}") from exc

    @staticmethod
    def _idempotent_schema_statement(statement: str) -> str:
        upper = statement.upper()
        marker = "CREATE TABLE "
        if marker in upper and "CREATE TABLE IF NOT EXISTS " not in upper:
            index = upper.index(marker)
            return (
                f"{statement[:index]}CREATE TABLE IF NOT EXISTS {statement[index + len(marker) :]}"
            )
        return statement

    def ensure_schema(self, sql: str) -> None:
        statements = [
            self._idempotent_schema_statement(statement.strip())
            for statement in sql.split(";")
            if statement.strip() and not statement.lstrip().upper().startswith(("GRANT", "REVOKE"))
        ]
        try:
            for statement in statements:
                self._client.command(statement)
        except Exception as exc:
            raise ClickHouseUnavailable(f"schema init failed: {exc}") from exc

    def persist_envelope(
        self,
        *,
        context: EncryptionContext,
        metadata: EncryptedEnvelopeMetadata,
        ciphertext_b64: str,
        key_generation: int,
    ) -> None:
        row = _phi_lookup_row_values(
            context,
            metadata,
            ciphertext_b64,
            key_generation,
        )
        try:
            self._client.insert("_phi_lookup", [row], column_names=self.COLUMN_ORDER)
        except Exception as exc:
            raise ClickHouseUnavailable(f"insert failed: {exc}") from exc

    def fetch_envelope(
        self, *, map_id: str | None = None, ciphertext_b64: str | None = None
    ) -> dict[str, Any]:
        if map_id is None and ciphertext_b64 is None:
            raise KeyProviderError("missing phi lookup key")
        if map_id is not None:
            where_clause = f"map_id = {_sql_quote(map_id)}"
        else:
            where_clause = f"ciphertext_b64 = {_sql_quote(str(ciphertext_b64))}"
        sql = (
            "SELECT " + ", ".join(self.COLUMN_ORDER) + f" FROM _phi_lookup WHERE {where_clause}"
            " ORDER BY inserted_at DESC LIMIT 1"
        )
        try:
            result = self._client.query(sql)
        except Exception as exc:
            raise ClickHouseUnavailable(f"lookup failed: {exc}") from exc
        if not getattr(result, "result_rows", None):
            raise KeyProviderError("phi lookup not found")
        row = dict(zip(self.COLUMN_ORDER, result.result_rows[0], strict=True))
        try:
            ciphertext = base64.urlsafe_b64decode(str(row["ciphertext_b64"]).encode("ascii"))
        except Exception as exc:
            raise KeyProviderError("invalid encrypted envelope encoding") from exc
        if hashlib.sha256(ciphertext).hexdigest() != str(row["ciphertext_sha256"]):
            raise KeyProviderError("ciphertext integrity mismatch")
        return row


_PHI_LOOKUP_STORE: ClickHousePhiLookupStore | None = None
_PHI_LOOKUP_STORE_FINGERPRINT: tuple[str, str, str, str, str] | None = None


def _phi_lookup_store() -> ClickHousePhiLookupStore | None:
    global _PHI_LOOKUP_STORE, _PHI_LOOKUP_STORE_FINGERPRINT
    config = _clickhouse_config_from_env()
    if config is None:
        _PHI_LOOKUP_STORE = None
        _PHI_LOOKUP_STORE_FINGERPRINT = None
        return None

    fingerprint = (
        config["host"],
        str(config["port"]),
        config["user"],
        config["password"],
        config["database"],
    )
    if _PHI_LOOKUP_STORE is not None and fingerprint == _PHI_LOOKUP_STORE_FINGERPRINT:
        return _PHI_LOOKUP_STORE

    store = ClickHousePhiLookupStore(**config, schema_sql=_load_phi_lookup_schema())
    _PHI_LOOKUP_STORE = store
    _PHI_LOOKUP_STORE_FINGERPRINT = fingerprint
    return store


def _metadata_from_dict(payload: dict[str, Any]) -> EncryptedEnvelopeMetadata:
    try:
        return EncryptedEnvelopeMetadata(
            key_id=KeyId(str(payload["key_id"])),
            algorithm=payload["algorithm"],
            schema_version=str(payload["schema_version"]),
            nonce_b64=str(payload["nonce_b64"]),
            aad_sha256=str(payload["aad_sha256"]),
        )
    except KeyError as exc:
        raise KeyProviderError("missing envelope metadata field") from exc


def _context_from_payload(
    payload: dict[str, Any], metadata: dict[str, Any] | None = None
) -> EncryptionContext:
    key_id = str(payload.get("key_id") or (metadata or {}).get("key_id") or DEFAULT_KEY_ID)
    return EncryptionContext(
        change_id=ChangeId(str(payload.get("change_id", "unknown"))),
        map_id=MapId(str(payload.get("map_id") or uuid.uuid4())),
        key_id=KeyId(key_id),
    )


def _span_text_sha256(text: str, start: int, end: int, provided: str | None) -> str:
    if provided:
        return provided
    return hashlib.sha256(text[start:end].encode("utf-8")).hexdigest()


def _length_preserving_placeholder(entity_type: str, text_sha256: str, length: int) -> str:
    sha8 = text_sha256[:8]
    preferred = f"{{{{ {PLACEHOLDER_PREFIX}_{entity_type}_{sha8} }}}}"
    if len(preferred) == length:
        return preferred
    if len(preferred) < length:
        return preferred + (" " * (length - len(preferred)))
    compact = f"{PLACEHOLDER_PREFIX}_{entity_type}_{sha8}"
    if len(compact) >= length:
        return compact[:length]
    return (compact + ("_" * length))[:length]


def _normalize_spans(request: dict[str, Any], text: str) -> list[dict[str, Any]]:
    spans = request.get("phi_spans")
    if isinstance(spans, list):
        return spans

    detected: list[dict[str, Any]] = []
    for entity_type, pattern, _token_code in SUBSTITUTIONS:
        for match in pattern.finditer(text):
            detected.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "entity_type": entity_type.replace("-", "_").upper(),
                    "score": 0.8,
                    "text_sha256": hashlib.sha256(match.group().encode("utf-8")).hexdigest(),
                }
            )
    return detected


def _build_desensitized_text_and_mapping(
    text: str, spans: list[dict[str, Any]]
) -> tuple[str, dict[str, str]]:
    chars = list(text)
    mapping: dict[str, str] = {}
    consumed_until = 0

    for span in sorted(spans, key=lambda item: (int(item["start"]), int(item["end"]))):
        start = int(span["start"])
        end = int(span["end"])
        if start < consumed_until or start < 0 or end > len(text) or start >= end:
            raise KeyProviderError("invalid or overlapping phi span")

        original = text[start:end]
        entity_type = str(span.get("entity_type", "UNKNOWN")).replace("-", "_").upper()
        text_sha256 = _span_text_sha256(text, start, end, span.get("text_sha256"))
        placeholder = _length_preserving_placeholder(entity_type, text_sha256, end - start)
        chars[start:end] = list(placeholder)
        mapping[placeholder] = original
        consumed_until = end

    desensitized_text = "".join(chars)
    if len(desensitized_text) != len(text):
        raise KeyProviderError("desensitized text length mismatch")
    return desensitized_text, mapping


def _active_key(provider: FileKeyProvider, key_id: str) -> tuple[bytes, int]:
    try:
        key = provider.get_key(key_id)
    except KeyNotFoundError:
        provider.rotate(key_id)
        key = provider.get_key(key_id)
    active_generation = provider.list_generations(key_id)[-1]
    return key, active_generation


def _persist_phi_lookup_envelope(
    context: EncryptionContext,
    metadata: EncryptedEnvelopeMetadata,
    map_ref: str,
    key_generation: int,
) -> None:
    store = _phi_lookup_store()
    if store is None:
        return
    store.persist_envelope(
        context=context,
        metadata=metadata,
        ciphertext_b64=map_ref,
        key_generation=key_generation,
    )


def _reverse_payload_from_lookup(request_payload: dict[str, Any]) -> dict[str, Any] | None:
    store = _phi_lookup_store()
    if store is None:
        return None
    map_id = _request_map_id(request_payload)
    ciphertext_b64 = request_payload.get("map_ref")
    row = store.fetch_envelope(
        map_id=map_id,
        ciphertext_b64=str(ciphertext_b64) if ciphertext_b64 is not None else None,
    )
    metadata = {
        "key_id": row["key_id"],
        "algorithm": row["algorithm"],
        "schema_version": row["schema_version"],
        "nonce_b64": row["nonce_b64"],
        "aad_sha256": row["aad_sha256"],
        "key_generation": row["key_generation"],
    }
    context = {
        "change_id": row["change_id"],
        "map_id": row["map_id"],
        "key_id": row["key_id"],
    }
    return {
        "map_ref": row["ciphertext_b64"],
        "metadata": metadata,
        "context": context,
    }


def desensitize(request: dict[str, Any], provider: FileKeyProvider | None = None) -> dict[str, Any]:
    provider = provider or _provider()
    text = request.get("text", request.get("payload", ""))
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    context_payload = request.get("context") if isinstance(request.get("context"), dict) else {}
    if "change_id" not in context_payload and "change_id" in request:
        context_payload["change_id"] = request["change_id"]
    if "map_id" not in context_payload:
        context_payload["map_id"] = str(uuid.uuid4())
    if "key_id" not in context_payload:
        context_payload["key_id"] = DEFAULT_KEY_ID

    context = _context_from_payload(context_payload)
    spans = _normalize_spans(request, text)
    desensitized_text, mapping = _build_desensitized_text_and_mapping(text, spans)
    key, key_generation = _active_key(provider, str(context.key_id))
    map_ref, metadata = encrypt_mapping(mapping, key, context)
    _persist_phi_lookup_envelope(context, metadata, map_ref, key_generation)
    metadata_dict = asdict(metadata)
    metadata_dict["key_generation"] = key_generation

    result: dict[str, Any] = {
        "desensitized_text": desensitized_text,
        "map_ref": map_ref,
        "metadata": metadata_dict,
    }
    try:
        if (
            key_generation - provider.list_generations(str(context.key_id))[0] + 1
            >= provider.max_generations
        ):
            result["warning"] = "old key generations must be migrated before prune"
    except Exception:
        pass
    return result


def _reverse_allowed(request: dict[str, Any]) -> bool:
    expected = os.environ.get(DEFAULT_REVERSE_TOKEN_ENV)
    token = request.get("kms_token")
    context = request.get("context")
    if token is None and isinstance(context, dict):
        token = context.get("kms_token")
    return bool(expected) and token == expected


def reverse(request: dict[str, Any], provider: FileKeyProvider | None = None) -> dict[str, Any]:
    if not _reverse_allowed(request):
        return {
            "error": {
                "type": "PermissionError",
                "message": "token invalid or missing; reverse denied",
            }
        }

    provider = provider or _provider()
    try:
        lookup_payload = _reverse_payload_from_lookup(request)
        envelope_payload = lookup_payload or request
        metadata_payload = envelope_payload.get("metadata")
        if not isinstance(metadata_payload, dict):
            raise KeyProviderError("missing envelope metadata")
        metadata = _metadata_from_dict(metadata_payload)
        context_payload = envelope_payload.get("context")
        if not isinstance(context_payload, dict):
            raise KeyProviderError("missing reverse context")
        context = _context_from_payload(context_payload, metadata_payload)
        generation = metadata_payload.get("key_generation")
        if generation is None:
            key = provider.get_key(str(context.key_id))
        else:
            key = provider.get_key_by_generation(str(context.key_id), int(generation))
        mapping = decrypt_mapping(str(envelope_payload.get("map_ref", "")), metadata, key, context)
    except Exception as exc:
        return {"error": _safe_error(exc)}
    return {"mapping": mapping}


def health() -> dict[str, str]:
    return {"status": "ok-v2", "crypto": "AES-256-GCM", "key_provider": "FileKeyProvider"}


def _response_for_request(
    req: dict[str, Any], provider: FileKeyProvider | None = None
) -> dict[str, Any]:
    method = req.get("method")
    params = req.get("params", {})
    if not isinstance(params, dict):
        params = {}
    if method == "desensitize":
        return {"id": req.get("id"), "result": desensitize(params, provider)}
    if method == "reverse":
        return {"id": req.get("id"), "result": reverse(params, provider)}
    if method == "health":
        return {"id": req.get("id"), "result": health()}
    return {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                response = _response_for_request(req)
            except Exception as exc:
                response = {"id": None, "error": _safe_error(exc)}
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0

    cmd = sys.argv[1] if len(sys.argv) > 1 else "desensitize"
    if cmd == "health":
        print(json.dumps(health(), ensure_ascii=False))
        return 0
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    if cmd == "desensitize":
        print(json.dumps(desensitize(req), ensure_ascii=False))
        return 0
    if cmd == "reverse":
        result = reverse(req)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if "error" in result else 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


desensitize_v2 = desensitize


if __name__ == "__main__":
    sys.exit(main())
