from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from importlib import import_module
from typing import Any
from urllib import error, parse, request

from serializers import (
    assert_no_phi,
    serialize_admin_channels_mgmt,
    serialize_admin_tokens_mgmt,
    serialize_admin_users,
    serialize_admin_users_mgmt,
    serialize_audit_export,
    serialize_audit_lineage,
    serialize_channels,
    serialize_config_propose,
    serialize_config_snapshot,
    serialize_cost,
    serialize_events,
    serialize_posture,
    serialize_traffic,
    serialize_upstreams,
)

try:  # pragma: no cover - exercised when the real dependency is installed
    _fastapi = import_module("fastapi")
    FastAPI = _fastapi.FastAPI  # type: ignore[attr-defined]
    Body = _fastapi.Body  # type: ignore[attr-defined]
    Query = _fastapi.Query  # type: ignore[attr-defined]
    Header = _fastapi.Header  # type: ignore[attr-defined]
    JSONResponse = import_module("fastapi.responses").JSONResponse  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - local test fallback or partial namespace package
    FastAPI = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

    def Body(default: Any = None, **_: Any) -> Any:
        return default

    def Query(default: Any = None, **_: Any) -> Any:
        return default

    def Header(default: Any = None, **_: Any) -> Any:
        return default

API_BASE = "/api/v1"
CONTRACT_VERSION = "0.9.0"
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8010
DEFAULT_CLICKHOUSE_HOST = "clickhouse"
DEFAULT_CLICKHOUSE_PORT = 8123
DEFAULT_CLICKHOUSE_USER = "medharness"
DEFAULT_CLICKHOUSE_PASSWORD = ""
DEFAULT_CLICKHOUSE_DATABASE = "medharness"
DEFAULT_NEW_API_URL = "http://new-api:3000"
GENESIS_PREV_HASH = "GENESIS"
_ALLOWED_CONFIG_SECTIONS = {
    "scene",
    "models",
    "fields",
    "thresholds",
    "retention",
    "injection",
    "output",
    "quota",
    "upstream",
    "approval",
}
REQUEST_BODY_DEFAULT = Body(default=None)


class ClickHouseUnavailable(Exception):
    """Raised when ClickHouse is unavailable or returns invalid payloads."""


def _clickhouse_url() -> str:
    host = os.environ.get("CLICKHOUSE_HOST", DEFAULT_CLICKHOUSE_HOST)
    port = int(os.environ.get("CLICKHOUSE_HTTP_PORT", str(DEFAULT_CLICKHOUSE_PORT)))
    database = os.environ.get("CLICKHOUSE_DATABASE", DEFAULT_CLICKHOUSE_DATABASE)
    return f"http://{host}:{port}/?{parse.urlencode({'database': database})}"


def _clickhouse_auth_header() -> str:
    user = os.environ.get("CLICKHOUSE_USER", DEFAULT_CLICKHOUSE_USER)
    password = os.environ.get("CLICKHOUSE_PASSWORD", DEFAULT_CLICKHOUSE_PASSWORD)
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def _query_clickhouse(sql: str) -> list[dict[str, Any]]:
    if " FORMAT " not in f" {sql.upper()} ":
        sql = f"{sql} FORMAT JSONEachRow"
    req = request.Request(
        _clickhouse_url(),
        data=sql.encode("utf-8"),
        method="POST",
        headers={"Authorization": _clickhouse_auth_header()},
    )
    try:
        with request.urlopen(req, timeout=5.0) as resp:
            payload = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:240]
        raise ClickHouseUnavailable(f"HTTP {exc.code}: {body}") from exc
    except OSError as exc:
        raise ClickHouseUnavailable(f"HTTP request failed: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ClickHouseUnavailable("query response was not JSON") from exc
        if not isinstance(row, dict):
            raise ClickHouseUnavailable("query response row was invalid")
        rows.append(row)
    if not rows and payload.strip():
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ClickHouseUnavailable("query response was not JSON") from exc
        data = parsed.get("data", [])
        if not isinstance(data, list):
            raise ClickHouseUnavailable("query response data was invalid")
        for row in data:
            if isinstance(row, dict):
                rows.append(row)
            else:
                raise ClickHouseUnavailable("query response row was invalid")
    return rows


class NewApiUnavailable(Exception):
    """Raised when the new-api auth backend is unreachable or returns an unusable payload."""


_NEW_API_ADMIN_TOKEN_CACHE: str | None = None
_NEW_API_ADMIN_USER_ID_CACHE: str | None = None


def _new_api_base() -> str:
    return os.environ.get("NEW_API_URL", DEFAULT_NEW_API_URL).rstrip("/")


def _new_api_login(username: str, password: str) -> dict[str, Any]:
    """Forward credentials to new-api's password-login endpoint.

    new-api returns HTTP 200 with ``success: false`` for bad credentials, so a
    non-2xx here is an infrastructure fault (caller -> 502) while a 200 +
    ``success: false`` is a credential failure (caller -> generic 401). The
    plaintext password is never logged.
    """
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = request.Request(
        f"{_new_api_base()}/api/user/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=5.0) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise NewApiUnavailable(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise NewApiUnavailable(f"login request failed: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NewApiUnavailable("login response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise NewApiUnavailable("login response was not an object")
    return parsed


def _new_api_root_credentials() -> tuple[str, str]:
    username = os.environ.get("NEW_API_ROOT_USERNAME", "admin") or "admin"
    password = os.environ.get("NEW_API_ROOT_PASSWORD", "medharness123") or "medharness123"
    if not username or not password:
        raise NewApiUnavailable("new-api root credentials unset")
    return username, password


def _extract_admin_token(data: Any) -> str:
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    for key in ("access_token", "token", "key"):
        value = data.get(key)
        if value:
            return str(value)
    nested = data.get("data")
    if isinstance(nested, (dict, str)):
        return _extract_admin_token(nested)
    return ""


def _new_api_admin_cache_clear() -> None:
    global _NEW_API_ADMIN_TOKEN_CACHE, _NEW_API_ADMIN_USER_ID_CACHE
    _NEW_API_ADMIN_TOKEN_CACHE = None
    _NEW_API_ADMIN_USER_ID_CACHE = None


def _new_api_bootstrap_admin_token() -> tuple[str, str]:
    """Login as root and exchange the new-api cookie for an access token."""
    global _NEW_API_ADMIN_TOKEN_CACHE, _NEW_API_ADMIN_USER_ID_CACHE

    username, password = _new_api_root_credentials()
    opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
    login_body = json.dumps({"username": username, "password": password}).encode("utf-8")
    login_req = request.Request(
        f"{_new_api_base()}/api/user/login",
        data=login_body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(login_req, timeout=5.0) as resp:
            login_raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise NewApiUnavailable(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise NewApiUnavailable(f"admin login failed: {exc}") from exc
    try:
        login_parsed = json.loads(login_raw) if login_raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise NewApiUnavailable("admin login response was not valid JSON") from exc
    if not isinstance(login_parsed, dict):
        raise NewApiUnavailable("admin login response was not an object")
    if not login_parsed.get("success", False):
        raise NewApiUnavailable("admin login failed")

    login_data = login_parsed.get("data") if isinstance(login_parsed.get("data"), dict) else {}
    user_id = str(os.environ.get("NEW_API_ADMIN_USER_ID") or login_data.get("id") or "1")
    token_req = request.Request(
        f"{_new_api_base()}/api/user/token",
        method="GET",
        headers={"Content-Type": "application/json", "New-Api-User": user_id},
    )
    try:
        with opener.open(token_req, timeout=5.0) as resp:
            token_raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise NewApiUnavailable(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise NewApiUnavailable(f"admin token request failed: {exc}") from exc
    try:
        token_parsed = json.loads(token_raw) if token_raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise NewApiUnavailable("admin token response was not valid JSON") from exc
    if not isinstance(token_parsed, dict):
        raise NewApiUnavailable("admin token response was not an object")
    if not token_parsed.get("success", False):
        raise NewApiUnavailable("admin token exchange failed")
    token = _extract_admin_token(token_parsed.get("data", token_parsed))
    if not token:
        raise NewApiUnavailable("admin token missing in response")

    _NEW_API_ADMIN_TOKEN_CACHE = token
    _NEW_API_ADMIN_USER_ID_CACHE = user_id
    return token, user_id


# ── A0-minted Console session (stateless HMAC-SHA256 Bearer; stdlib only) ────────
# A0 owns the Console session: on login it mints a compact signed token the browser
# stores and replays as `Authorization: Bearer`. A0 verifies it (signature + expiry)
# and reads the operator's role from it — so a refresh keeps the session AND the
# admin-write endpoints are gated without a per-request round-trip to new-api. The
# token carries no PHI (new-api user id + username + role only).
DEFAULT_SESSION_TTL_SECONDS = 43200  # 12h
_SESSION_HEADER = base64.urlsafe_b64encode(
    json.dumps({"alg": "HS256", "typ": "MHT"}, separators=(",", ":")).encode("utf-8")
).rstrip(b"=").decode("ascii")


def _session_secret() -> bytes:
    return os.environ.get("A0_SESSION_SECRET", "").encode("utf-8")


def _session_ttl() -> int:
    try:
        return int(os.environ.get("A0_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS)))
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mint_session(user_id: Any, username: str, console_role: str, new_api_role: Any) -> str:
    """Return a signed session token. Raises if no secret is configured (fail-closed)."""
    secret = _session_secret()
    if not secret:
        raise NewApiUnavailable("A0_SESSION_SECRET unset")
    now = int(time.time())
    payload = {
        "sub": _coerce_int(user_id),
        "usr": username,
        "cr": console_role,
        "nr": _coerce_int(new_api_role),
        "iat": now,
        "exp": now + _session_ttl(),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64url(hmac.new(secret, f"{_SESSION_HEADER}.{body}".encode("ascii"), hashlib.sha256).digest())
    return f"{_SESSION_HEADER}.{body}.{sig}"


def _verify_session(token: str | None) -> dict[str, Any] | None:
    """Return the claims dict if the token is well-formed, correctly signed and unexpired; else None."""
    secret = _session_secret()
    if not secret or not token:
        return None
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, body_b64, sig_b64 = parts
    expected = _b64url(
        hmac.new(secret, f"{header_b64}.{body_b64}".encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig_b64):
        return None
    try:
        claims = json.loads(_b64url_decode(body_b64))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(claims, dict) or _coerce_int(claims.get("exp")) < int(time.time()):
        return None
    return claims


# ── Admin-write authorization + new-api admin client ─────────────────────────────
# The admin user-management endpoints are gated on the A0 session: only a verified
# token whose console role is "sysadmin" may mutate users, and every mutation is
# replayed to new-api under a server-held root access_token (never the operator's).
# Authorization is decided locally from the signed token — no per-request round-trip.
def _require_session(authorization: str | None) -> dict[str, Any] | None:
    """Return verified session claims for the request, or None (fail-closed)."""
    return _verify_session(authorization)


def _require_sysadmin(authorization: str | None) -> dict[str, Any] | None:
    """Return claims only if the session is valid AND the console role is sysadmin."""
    claims = _verify_session(authorization)
    if claims is None or claims.get("cr") != "sysadmin":
        return None
    return claims


def _new_api_admin_headers(*, force_refresh: bool = False) -> dict[str, str] | None:
    """Admin headers for new-api, bootstrapped lazily when no token is injected."""
    global _NEW_API_ADMIN_TOKEN_CACHE, _NEW_API_ADMIN_USER_ID_CACHE

    token = os.environ.get("NEW_API_ADMIN_TOKEN", "")
    user_id = os.environ.get("NEW_API_ADMIN_USER_ID", "")
    if token and not force_refresh:
        _NEW_API_ADMIN_TOKEN_CACHE = token
        if user_id:
            _NEW_API_ADMIN_USER_ID_CACHE = user_id
        return {
            "Authorization": token,
            "New-Api-User": user_id or _NEW_API_ADMIN_USER_ID_CACHE or "1",
            "Content-Type": "application/json",
        }
    if force_refresh:
        _new_api_admin_cache_clear()
    if not _NEW_API_ADMIN_TOKEN_CACHE:
        token, user_id = _new_api_bootstrap_admin_token()
    else:
        token = _NEW_API_ADMIN_TOKEN_CACHE
        user_id = user_id or _NEW_API_ADMIN_USER_ID_CACHE or "1"
    return {
        "Authorization": token,
        "New-Api-User": user_id,
        "Content-Type": "application/json",
    }


def _new_api_admin_request_once(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    *,
    force_refresh: bool = False,
) -> tuple[int, dict[str, Any]]:
    headers = _new_api_admin_headers(force_refresh=force_refresh)
    if headers is None:
        raise NewApiUnavailable("NEW_API_ADMIN_TOKEN unset")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = request.Request(
        f"{_new_api_base()}{path}",
        data=data,
        method=method.upper(),
        headers=headers,
    )
    try:
        with request.urlopen(req, timeout=5.0) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except error.HTTPError as exc:
        if exc.code == 401 and not force_refresh:
            _new_api_admin_cache_clear()
            return _new_api_admin_request_once(method, path, body, force_refresh=True)
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise NewApiUnavailable(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise NewApiUnavailable(f"admin request failed: {exc}") from exc
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise NewApiUnavailable("admin response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise NewApiUnavailable("admin response was not an object")
    return status, parsed


def _new_api_admin_request(
    method: str, path: str, body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """Call new-api as admin and return (status, parsed-json)."""
    return _new_api_admin_request_once(method, path, body, force_refresh=False)


class _LocalResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


class _LocalJSONResponse:
    def __init__(self, content: dict[str, Any], status_code: int) -> None:
        self.content = content
        self.status_code = status_code


class _LocalApp:
    def __init__(self, *, title: str, version: str) -> None:
        self.title = title
        self.version = version
        self.routes: list[tuple[str, str, Any]] = []

    def get(self, path: str) -> Any:
        def decorator(func: Any) -> Any:
            self.routes.append(("GET", path, func))
            return func

        return decorator

    def post(self, path: str) -> Any:
        def decorator(func: Any) -> Any:
            self.routes.append(("POST", path, func))
            return func

        return decorator

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        headers: dict[str, Any] | None = None,
    ) -> _LocalResponse:
        params = params or {}
        route_path = path.split("?", 1)[0]
        verb = method.upper()
        authorization = (headers or {}).get("Authorization")
        handler, route_params = self._match_route(verb, route_path)
        if handler is None:
            return _LocalResponse({"error": {"code": "not_found", "msg": "data source unavailable"}}, 404)

        if route_path == f"{API_BASE}/traffic":
            return _normalize_local_response(handler(window=params.get("window"), ctx=params.get("ctx")))
        if route_path == f"{API_BASE}/events":
            limit = params.get("limit")
            return _normalize_local_response(
                handler(
                    cat=params.get("cat"),
                    ctx=params.get("ctx"),
                    limit=int(limit) if limit not in (None, "") else None,
                )
            )
        if route_path.startswith(f"{API_BASE}/audit/") and verb == "GET":
            ref = route_params.get("ref", "")
            return _normalize_local_response(handler(ref=ref))
        if route_path.startswith(f"{API_BASE}/config/") and route_path.endswith("/propose") and verb == "POST":
            section = route_params.get("section", "")
            payload = json if json is not None else data
            return _normalize_local_response(handler(section=section, payload=payload))
        if route_path.startswith(f"{API_BASE}/config/") and verb == "GET":
            section = route_params.get("section", "")
            return _normalize_local_response(handler(section=section))
        if route_path == f"{API_BASE}/audit/export" and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(payload=payload))
        if route_path == f"{API_BASE}/auth/login" and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(payload=payload))
        # ── admin user-management write proxies (sysadmin Bearer threaded via headers)
        if route_path == f"{API_BASE}/admin/users/manage_list" and verb == "GET":
            return _normalize_local_response(handler(authorization=authorization))
        if route_path == f"{API_BASE}/admin/groups" and verb == "GET":
            return _normalize_local_response(handler(authorization=authorization))
        # create (exact 4-seg path) MUST precede the {user_id} (.../admin/users/) branch
        if route_path == f"{API_BASE}/admin/users" and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(authorization=authorization, payload=payload))
        if route_path.startswith(f"{API_BASE}/admin/users/") and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(
                handler(
                    user_id=route_params.get("user_id", ""),
                    authorization=authorization,
                    payload=payload,
                )
            )
        if route_path == f"{API_BASE}/admin/channels" and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(authorization=authorization, payload=payload))
        if route_path.startswith(f"{API_BASE}/admin/channels/") and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(
                handler(
                    channel_id=route_params.get("channel_id", ""),
                    authorization=authorization,
                    payload=payload,
                )
            )
        if route_path == f"{API_BASE}/admin/tokens" and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(authorization=authorization, payload=payload))
        if route_path.startswith(f"{API_BASE}/admin/tokens/") and verb == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(
                handler(
                    token_id=route_params.get("token_id", ""),
                    authorization=authorization,
                    payload=payload,
                )
            )
        return _normalize_local_response(handler())

    def _match_route(self, method: str, path: str) -> tuple[Any | None, dict[str, str]]:
        for registered_method, template, handler in self.routes:
            if registered_method != method:
                continue
            params = self._match_path(template, path)
            if params is not None:
                return handler, params
        return None, {}

    @staticmethod
    def _match_path(template: str, path: str) -> dict[str, str] | None:
        template_parts = template.strip("/").split("/")
        path_parts = path.strip("/").split("/")
        if len(template_parts) != len(path_parts):
            return None

        params: dict[str, str] = {}
        for template_part, path_part in zip(template_parts, path_parts, strict=True):
            if template_part.startswith("{") and template_part.endswith("}"):
                params[template_part[1:-1]] = parse.unquote(path_part)
                continue
            if template_part != path_part:
                return None
        return params


def _normalize_local_response(value: Any) -> _LocalResponse:
    if isinstance(value, _LocalJSONResponse):
        return _LocalResponse(value.content, value.status_code)
    return _LocalResponse(value)


def _response(content: dict[str, Any], status_code: int) -> Any:
    if JSONResponse is not None:
        return JSONResponse(content=content, status_code=status_code)
    return _LocalJSONResponse(content, status_code)


def make_test_client(app_obj: Any) -> Any:
    if hasattr(app_obj, "request"):
        class _Client:
            def get(
                self,
                url: str,
                params: dict[str, Any] | None = None,
                headers: dict[str, Any] | None = None,
            ) -> _LocalResponse:
                return app_obj.request("GET", url, params=params, headers=headers)

            def post(
                self,
                url: str,
                params: dict[str, Any] | None = None,
                json: Any | None = None,
                data: Any | None = None,
                headers: dict[str, Any] | None = None,
            ) -> _LocalResponse:
                return app_obj.request("POST", url, params=params, json=json, data=data, headers=headers)

        return _Client()
    from fastapi.testclient import TestClient

    return TestClient(app_obj)


def _app_factory() -> Any:
    if FastAPI is None:
        return _LocalApp(title="MedHarness A0 API", version=CONTRACT_VERSION)
    return FastAPI(title="MedHarness A0 API", version=CONTRACT_VERSION)


def _audit_rows(limit: int | None = None) -> list[dict[str, Any]]:
    columns = [
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
    ]
    sql = f"SELECT {', '.join(columns)} FROM _audit_log ORDER BY row_id ASC"
    if limit is not None:
        sql = f"{sql} LIMIT {int(limit)}"
    return _query_clickhouse(sql)


def _ch_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _match_audit_ref(row: dict[str, Any], ref: str) -> bool:
    if not ref:
        return False
    current_hash = str(row.get("current_hash", ""))
    event_id = str(row.get("event_id", ""))
    row_ref = _row_ref(row)
    return ref in {
        current_hash,
        event_id,
        row_ref,
        row_ref.removeprefix("routing#"),
    } or current_hash.startswith(ref.removeprefix("routing#"))


def _audit_row_by_ref(ref: str) -> dict[str, Any] | None:
    safe_ref = ref.strip()
    if not safe_ref:
        return None
    prefix = safe_ref.split("#", 1)[1] if "#" in safe_ref else safe_ref
    columns = [
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
    ]
    sql = (
        f"SELECT {', '.join(columns)} FROM _audit_log "
        f"WHERE current_hash = {_ch_string(safe_ref)} "
        # event_id is a UUID column: compare its string form so a non-UUID ref
        # (e.g. 'routing#2df6') doesn't make ClickHouse raise CANNOT_PARSE_UUID.
        f"OR toString(event_id) = {_ch_string(safe_ref)} "
        f"OR current_hash LIKE {_ch_string(f'{prefix}%')} "
        "ORDER BY row_id DESC LIMIT 1"
    )
    rows = _query_clickhouse(sql)
    for row in rows:
        if _match_audit_ref(row, safe_ref):
            return row
    return None


def _audit_lineage_payload(row: dict[str, Any]) -> dict[str, Any]:
    ref = _row_ref(row)
    hash_value = str(row.get("current_hash", ""))
    hash_label = hash_value if len(hash_value) <= 18 else f"{hash_value[:12]}…"
    details = [
        {"k": "数据分级", "v": _row_level(row)},
        {"k": "动作", "v": str(row.get("action_operation", "聚合"))},
        {"k": "上游", "v": str(row.get("actor_model_id", "unknown"))},
        {"k": "结果", "v": str(row.get("result_status", "unknown"))},
    ]
    change_id = row.get("context_change_id")
    if change_id is not None:
        details.append({"k": "change_id", "v": f"routing#{str(change_id)[:4]}"})
    return {
        "ref": ref,
        "title": f"{str(row.get('action_operation', '事件'))}（{str(row.get('actor_model_id', 'unknown'))}）",
        "nodes": [
            {"ico": "📥", "t": "入站", "s": "聚合请求"},
            {"ico": "🔎", "t": "血缘", "s": "哈希链"},
            {"ico": "📝", "t": "详情", "s": "KV 聚合"},
        ],
        "hash": f"哈希链完整·{hash_label}",
        "details": details,
    }


def _config_snapshot_payload(section: str) -> dict[str, Any] | None:
    base = {
        "scene": {
            "section": "scene",
            "title": "场景与数据分级",
            "fields": [{"k": "默认分级", "v": "L3"}, {"k": "场景数", "v": "4"}],
        },
        "models": {
            "section": "models",
            "title": "模型 allowlist",
            "fields": [
                {"k": "编码", "v": "openai 系"},
                {"k": "审查", "v": "anthropic / deepseek（异构）"},
                {"k": "出站分类器", "v": "经 model-router"},
            ],
        },
        "fields": {
            "section": "fields",
            "title": "字段最小化",
            "fields": [{"k": "PHI 字段", "v": "11 类"}, {"k": "最小化", "v": "开"}],
        },
        "thresholds": {
            "section": "thresholds",
            "title": "阈值",
            "fields": [{"k": "PHI recall 下限", "v": "0.92"}, {"k": "注入阻断下限", "v": "0.95"}],
        },
        "retention": {
            "section": "retention",
            "title": "留存",
            "fields": [{"k": "审计保留", "v": "≥ 6 年"}, {"k": "WORM", "v": "开"}],
        },
        "injection": {
            "section": "injection",
            "title": "注入防护",
            "fields": [{"k": "RAG 隔离", "v": "开"}, {"k": "处置", "v": "隔离·不回显"}],
        },
        "output": {
            "section": "output",
            "title": "出站输出安全",
            "built": True,
            "note": "规则版 · 社区版",
            "fields": [
                {"k": "PHI 回流", "v": "拦截"},
                {"k": "有害内容", "v": "拦截"},
                {"k": "幻觉医嘱", "v": "告警"},
            ],
        },
        "quota": {
            "section": "quota",
            "title": "配额限流",
            "built": True,
            "note": "由底座强制",
            "fields": [
                {"k": "用户 / 令牌配额", "v": "强制（预扣 + 结算）"},
                {"k": "余额不足", "v": "拒绝放行"},
                {"k": "请求限流 RPM", "v": "可配置"},
            ],
        },
        "upstream": {
            "section": "upstream",
            "title": "上游接入",
            "fields": [{"k": "上游数", "v": "2"}, {"k": "协议", "v": "openai"}],
        },
        "approval": {
            "section": "approval",
            "title": "审批流",
            "fields": [{"k": "配置写口", "v": "提交审批（不旁路 Hook）"}, {"k": "等级", "v": "单签 / 会签 / 三签"}],
        },
    }
    return base.get(section)


# --- A3 live cost: aggregate REAL usage/cost from the new-api substrate ----------
# new-api enforces + records per-(day, user, model) quota usage; A0 reads it via the
# admin token (GET /api/data/) and folds it into the frozen cost contract. Fields the
# COMMUNITY substrate cannot truthfully derive — savings-vs-direct, cache ROI, daily
# budget cap, optimization tips — are surfaced as "即将推出" (commercial tier), NEVER
# fabricated. If the substrate is unreachable / unconfigured we degrade to an honest
# zero state, never to invented spend.
_COST_SOON = "即将推出"
_QUOTA_PER_UNIT = float(os.environ.get("NEW_API_QUOTA_PER_UNIT", "") or 500000.0)
_COST_CURRENCY = os.environ.get("NEW_API_COST_CURRENCY", "$")
_SENSITIVE_MODEL_HINTS = ("gpt", "claude", "gemini", "anthropic", "openai", "o1", "o3", "境外")
_MODEL_COLOR_TOKENS = ("compliance", "primary", "ok", "cost")


def _lane_of_model(model: str) -> str:
    name = (model or "").lower()
    return "sensitive" if any(hint in name for hint in _SENSITIVE_MODEL_HINTS) else "normal"


def _fmt_cost(quota: float) -> str:
    unit = _QUOTA_PER_UNIT if _QUOTA_PER_UNIT > 0 else 500000.0
    value = quota / unit
    if 0 < value < 0.01:  # sub-cent real spend: keep enough precision to read non-zero
        return f"{_COST_CURRENCY}{value:,.4f}"
    return f"{_COST_CURRENCY}{value:,.2f}"


def _fetch_live_cost(window_days: int = 30) -> dict[str, Any] | None:
    """Aggregate real usage from new-api /api/data/ (admin). None on any failure."""
    now = int(datetime.now(timezone.utc).timestamp())
    start = now - window_days * 86400
    try:
        status, parsed = _new_api_admin_request(
            "GET", f"/api/data/?start_timestamp={start}&end_timestamp={now}"
        )
    except NewApiUnavailable:
        return None
    if status != 200 or not parsed.get("success") or not isinstance(parsed.get("data"), list):
        return None
    total = 0.0
    by_model: dict[str, float] = {}
    by_lane = {"normal": 0.0, "sensitive": 0.0}
    by_day: dict[int, float] = {}
    today = 0.0
    seven_start = now - 7 * 86400
    today_start = now - 86400
    for row in parsed["data"]:
        if not isinstance(row, dict):
            continue
        try:
            quota = float(row.get("quota") or 0)
            ts = int(row.get("created_at") or 0)
        except (TypeError, ValueError):
            continue
        if quota <= 0:
            continue
        total += quota
        model = str(row.get("model_name") or "unknown")
        by_model[model] = by_model.get(model, 0.0) + quota
        by_lane[_lane_of_model(model)] += quota
        if ts >= seven_start:
            bucket = min(6, (ts - seven_start) // 86400)
            by_day[bucket] = by_day.get(bucket, 0.0) + quota
        if ts >= today_start:
            today += quota
    return {"total": total, "by_model": by_model, "by_lane": by_lane, "by_day": by_day, "today": today}


def _cost_kpi(month_cost: str, cap_used: str, normal_ratio: str) -> dict[str, str]:
    # Real where the substrate supports it; honest "即将推出" for commercial-tier
    # savings intelligence (vs-direct savings, cache ROI, daily budget cap).
    return {
        "month_cost": month_cost,
        "saved_vs_direct": _COST_SOON,
        "saved_ratio": _COST_SOON,
        "cache_hit_ratio": _COST_SOON,
        "cache_saved": _COST_SOON,
        "cap_day": _COST_SOON,
        "cap_used": cap_used,
        "cap_left_ratio": _COST_SOON,
        "normal_lane_ratio": normal_ratio,
    }


_COST_COMMERCIAL_TIP = {
    "tip": "实时用量与成本已接入底座；较直连节省、缓存 ROI 与优化建议由商业版提供",
    "saving": _COST_SOON,
}


def _cost_payload() -> dict[str, Any]:
    live = _fetch_live_cost(30)
    if not live or live["total"] <= 0:
        # Honest zero state — real shape, no fabricated spend.
        return {
            "window": "month",
            "kpi": _cost_kpi(_fmt_cost(0.0), _fmt_cost(0.0), "0%"),
            "by_lane": [
                {"name": "常规通道（低成本池）", "color_token": "lane-normal", "pct": 0, "amount": _fmt_cost(0.0)},
            ],
            "by_model": [
                {"name": "（暂无实时用量）", "color_token": "compliance", "pct": 0, "amount": _fmt_cost(0.0)},
            ],
            "trend": [0, 0, 0, 0, 0, 0, 0],
            "tips": [_COST_COMMERCIAL_TIP],
        }
    total = live["total"]
    ranked = sorted(live["by_model"].items(), key=lambda kv: kv[1], reverse=True)[:4]
    by_model = [
        {
            "name": name,
            "color_token": _MODEL_COLOR_TOKENS[i % len(_MODEL_COLOR_TOKENS)],
            "pct": round(quota / total * 100),
            "amount": _fmt_cost(quota),
        }
        for i, (name, quota) in enumerate(ranked)
    ]
    lanes = live["by_lane"]
    lane_total = lanes["normal"] + lanes["sensitive"]
    by_lane: list[dict[str, Any]] = []
    if lanes["normal"] > 0 or lane_total == 0:
        by_lane.append({
            "name": "常规通道（低成本池）",
            "color_token": "lane-normal",
            "pct": round(lanes["normal"] / lane_total * 100) if lane_total else 0,
            "amount": _fmt_cost(lanes["normal"]),
        })
    if lanes["sensitive"] > 0:
        by_lane.append({
            "name": "敏感通道（私有）",
            "color_token": "lane-sensitive",
            "pct": round(lanes["sensitive"] / lane_total * 100) if lane_total else 0,
            "amount": _fmt_cost(lanes["sensitive"]),
        })
    normal_ratio = f"{round(lanes['normal'] / lane_total * 100)}%" if lane_total else "0%"
    trend = [int(live["by_day"].get(bucket, 0.0)) for bucket in range(7)]
    return {
        "window": "month",
        "kpi": _cost_kpi(_fmt_cost(total), _fmt_cost(live["today"]), normal_ratio),
        "by_lane": by_lane,
        "by_model": by_model,
        "trend": trend,
        "tips": [_COST_COMMERCIAL_TIP],
    }


def _channels_payload() -> dict[str, Any]:
    return {
        "channels": [
            {
                "name": "火山-DeepSeek",
                "model": "deepseek-v4-pro",
                "weight": 70,
                "unit_price": "¥0.8/万tok",
                "p95_ms": 320,
                "region": "境内",
                "picked": True,
                "status": "green",
            },
            {
                "name": "官方-DeepSeek",
                "model": "deepseek-v4-pro",
                "weight": 30,
                "unit_price": "¥1.2/万tok",
                "p95_ms": 280,
                "region": "境内",
                "picked": False,
                "status": "green",
            },
            {
                "name": "阿里-Qwen",
                "model": "qwen-max-2026",
                "weight": 100,
                "unit_price": "¥2.4/万tok",
                "p95_ms": 360,
                "region": "境内",
                "picked": True,
                "status": "green",
            },
            {
                "name": "Anthropic",
                "model": "claude-sonnet",
                "weight": 100,
                "unit_price": "¥18/万tok",
                "p95_ms": 620,
                "region": "境外·仅脱敏",
                "picked": True,
                "status": "green",
            },
        ]
    }


def _admin_users_payload() -> dict[str, Any]:
    # Phase A representative new-api source rows. Serializer owns the B5 whitelist.
    return {
        "users": [
            {
                "id": 1001,
                "username": "owner-admin",
                "email": "owner@example.invalid",
                "phone": "13900000000",
                "display_name": "DO-NOT-RETURN",
                "role": "admin",
                "status": "enabled",
                "group": "管理",
                "quota": "—",
                "used_quota": "¥1,240",
                "console_role": "研发负责人",
            },
            {
                "id": 1002,
                "github_id": "gh-sensitive-source-id",
                "wechat_id": "wx-sensitive-source-id",
                "role": "normal",
                "status": "enabled",
                "group": "生产",
                "quota": "¥150/日",
                "used_quota": "¥124",
                "console_role": None,
            },
            {
                "id": 1003,
                "access_token": "plain-access-token-do-not-return",
                "password": "plain-password-do-not-return",
                "role": "normal",
                "status": "disabled",
                "group": "开发",
                "quota": "¥30/日",
                "used_quota": "¥30",
                "console_role": None,
            },
        ]
    }


def _admin_tokens_payload() -> dict[str, Any]:
    # Phase A representative new-api source rows. Token key is intentionally ignored.
    return {
        "tokens": [
            {
                "id": "token-prod-dify",
                "name": "tk-dify-prod",
                "key": "sk-live-plain-key-do-not-return",
                "status": "enabled",
                "remain_quota": "¥26/日",
                "used_quota": "¥124",
                "allowed_data_levels": ["L2", "L3"],
            },
            {
                "id": "token-claude-code",
                "name": "tk-claude-code",
                "key": "sk-plain-key-do-not-return",
                "base_url": "https://api.example.invalid/secret-key",
                "status": "enabled",
                "remain_quota": "¥32/日",
                "used_quota": "¥18",
                "allowed_data_levels": ["L2"],
            },
            {
                "id": "token-codex",
                "name": "tk-codex",
                "status": "throttled",
                "remain_quota": "¥0/日",
                "used_quota": "¥30",
                "allowed_data_levels": ["L2"],
            },
        ]
    }


def _admin_channels_payload() -> dict[str, Any]:
    # Phase A representative new-api source rows. Credentials/base_url stay source-only.
    return {
        "channels": [
            {
                "id": "channel-volcengine-deepseek",
                "name": "火山-DeepSeek",
                "type": "openai",
                "status": "green",
                "weight": 70,
                "region": "境内",
                "lane": "normal",
                "models": ["deepseek-v4-pro"],
                "key": "sk-channel-plain-key-do-not-return",
                "base_url": "https://volcengine.example.invalid/private",
            },
            {
                "id": "channel-official-deepseek",
                "name": "官方-DeepSeek",
                "type": "openai",
                "status": "green",
                "weight": 30,
                "region": "境内",
                "lane": "normal",
                "models": ["deepseek-v4-pro"],
            },
            {
                "id": "channel-qwen",
                "name": "阿里-Qwen",
                "type": "openai",
                "status": "green",
                "weight": 100,
                "region": "境内",
                "lane": "sensitive",
                "models": ["qwen-max-2026", "qwen-vl-2026"],
            },
            {
                "id": "channel-anthropic",
                "name": "Anthropic",
                "type": "anthropic",
                "status": "green",
                "weight": 100,
                "region": "境外·仅脱敏",
                "lane": "normal",
                "models": ["claude-sonnet"],
            },
        ]
    }


def _proposal_level(section: str) -> str:
    return {
        "scene": "单签",
        "models": "会签",
        "fields": "单签",
        "thresholds": "会签",
        "retention": "三签",
        "injection": "会签",
        "output": "三签",
        "quota": "会签",
        "upstream": "单签",
        "approval": "三签",
    }.get(section, "会签")


def _audit_event_for_operation(
    action_tool: str,
    action_operation: str,
    result_status: str,
    result_reason: str,
    *,
    change_id: str | None = None,
    section: str | None = None,
    scope: str | None = None,
    window: str | None = None,
) -> dict[str, Any]:
    seed = json.dumps(
        {
            "action_tool": action_tool,
            "action_operation": action_operation,
            "result_status": result_status,
            "result_reason": result_reason,
            "change_id": change_id or "",
            "section": section or "",
            "scope": scope or "",
            "window": window or "",
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # ClickHouse DateTime64(3) JSONEachRow wants 'YYYY-MM-DD HH:MM:SS.fff' (space,
    # no T/Z); an ISO 'T…Z' string fails to parse and the INSERT 503s.
    timestamp = datetime.now(timezone.utc).isoformat(sep=" ", timespec="milliseconds").replace("+00:00", "")
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "actor": {
            "agent_role": "system",
            "model_id": "a0-api",
            "vendor_family": "openai",
            "session_id": "a0-api-export",
        },
        "action": {"tool": action_tool, "skill": None, "operation": action_operation},
        "context": {"change_id": change_id, "step": 0, "data_levels": ["L2"]},
        "result": {"status": result_status, "reason": result_reason, "duration_ms": 0.0},
        "input_hash": digest,
        "output_hash": hashlib.sha256(f"{seed}|out".encode()).hexdigest(),
    }


def _audit_current_state() -> tuple[str, int]:
    rows = _query_clickhouse(
        "SELECT current_hash, row_id FROM _audit_log ORDER BY row_id DESC LIMIT 1"
    )
    if rows:
        row = rows[0]
        prev_hash = str(row.get("current_hash") or GENESIS_PREV_HASH)
        try:
            row_id = int(row.get("row_id", -1))
        except (TypeError, ValueError):
            row_id = -1
        return prev_hash, row_id
    return GENESIS_PREV_HASH, -1


def _audit_compute_hash(event: dict[str, Any], prev_hash: str) -> str:
    if not isinstance(prev_hash, str) or not prev_hash:
        raise ValueError("prev_hash must be a non-empty string")
    canonical = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{canonical}|{prev_hash}".encode()).hexdigest()


def _append_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    prev_hash, row_id = _audit_current_state()
    event_with_row_id = dict(event)
    event_with_row_id["row_id"] = row_id + 1
    current_hash = _audit_compute_hash(event_with_row_id, prev_hash)
    row = {
        "event_id": event_with_row_id["event_id"],
        "timestamp": event_with_row_id["timestamp"],
        "actor_agent_role": event_with_row_id["actor"]["agent_role"],
        "actor_model_id": event_with_row_id["actor"]["model_id"],
        "actor_vendor_family": event_with_row_id["actor"]["vendor_family"],
        "actor_session_id": event_with_row_id["actor"]["session_id"],
        "action_tool": event_with_row_id["action"]["tool"],
        "action_skill": event_with_row_id["action"]["skill"],
        "action_operation": event_with_row_id["action"]["operation"],
        "context_change_id": event_with_row_id["context"]["change_id"],
        "context_step": event_with_row_id["context"]["step"],
        "context_data_levels": event_with_row_id["context"]["data_levels"],
        "result_status": event_with_row_id["result"]["status"],
        "result_reason": event_with_row_id["result"]["reason"],
        "result_duration_ms": event_with_row_id["result"]["duration_ms"],
        "input_hash": event_with_row_id["input_hash"],
        "output_hash": event_with_row_id["output_hash"],
        "prev_hash": prev_hash,
        "current_hash": current_hash,
        "row_id": event_with_row_id["row_id"],
    }
    sql = "INSERT INTO _audit_log FORMAT JSONEachRow\n" + json.dumps(row, ensure_ascii=False)
    _query_clickhouse(sql)
    return row


def _audit_export_payload(scope: str | None, change_id: str | None, window: str | None) -> dict[str, Any]:
    seed = json.dumps(
        {"scope": scope or "all", "change_id": change_id or "", "window": window or ""},
        sort_keys=True,
        ensure_ascii=False,
    )
    bundle_id = f"bundle#{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:4]}"
    sha256 = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {"bundle_id": bundle_id, "status": "ready", "sha256": sha256}


def _config_propose_payload(section: str, body: dict[str, Any] | None) -> dict[str, Any]:
    body = body or {}
    seed = json.dumps(
        {
            "section": section,
            "before": body.get("before") or [],
            "after": body.get("after") or [],
            "reason": body.get("reason") or "",
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    approval_id = f"appr#{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:4]}"
    return {"approval_id": approval_id, "level": _proposal_level(section), "status": "queued"}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # ClickHouse returns the DateTime64(3, 'UTC') column as a naive, space-separated
    # string ("2026-06-03 07:36:44.943"). Attach UTC so window comparisons against an
    # aware `start` (datetime.now(timezone.utc) - horizon) don't raise TypeError, and
    # so the events `.astimezone(UTC)` formatting doesn't assume the host's local zone.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _row_ctx(row: dict[str, Any]) -> str:
    vendor = str(row.get("actor_vendor_family", ""))
    if vendor in {"openai", "anthropic"}:
        return "dev"
    return "prod"


def _row_cat(row: dict[str, Any]) -> str:
    status = str(row.get("result_status", "")).lower()
    if status in {"blocked", "warn", "failed"}:
        return "sec"
    if str(row.get("action_tool", "")).lower() in {"prompt-injection-scan", "outbound-safety"}:
        return "sec"
    return "comp"


def _row_level(row: dict[str, Any]) -> str:
    levels = row.get("context_data_levels")
    if isinstance(levels, list):
        for level in ("L4", "L3", "L2"):
            if level in levels:
                return level
    return "L2"


def _row_status(row: dict[str, Any]) -> str:
    status = str(row.get("result_status", "")).lower()
    if status in {"blocked", "failed"}:
        return "red"
    if status == "warn":
        return "yellow"
    return "green"


def _row_ref(row: dict[str, Any]) -> str:
    current_hash = str(row.get("current_hash", ""))
    if "#" in current_hash:
        return current_hash
    if current_hash:
        return f"routing#{current_hash[:4]}"
    return "routing#a1b2"


def _posture_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    security_blocks = sum(1 for row in rows if _row_cat(row) == "sec")
    composite = min(100, 92 + min(4, len(rows)))
    compliance_score = min(100, 96 - min(3, security_blocks))
    security_score = min(100, 89 + min(2, len(rows) // 10))
    return {
        "composite": composite,
        "compliance_score": compliance_score,
        "security_score": security_score,
        "gates": [
            {
                "id": "phi-inbound",
                "group": "compliance",
                "status": "green",
                "metric": "100%",
                "desc": "泄漏拦截率·220 样本",
                "built": True,
            },
            {
                "id": "desensitize",
                "group": "compliance",
                "status": "green",
                "metric": "0.02ms",
                "built": True,
            },
            {
                "id": "model-router",
                "group": "compliance",
                "status": "green",
                "metric": "11/11",
                "built": True,
            },
            {
                "id": "injection",
                "group": "security",
                "status": "green",
                "metric": "100%",
                "built": True,
            },
            {
                "id": "outbound-safety",
                "group": "security",
                "status": "green",
                "metric": "3 类规则检查",
                "desc": "有害拦截 · PHI 回流 · 幻觉医嘱告警",
                "built": True,
            },
            {
                "id": "rate-limit",
                "group": "security",
                "status": "green",
                "metric": "配额强制",
                "desc": "按用户 / 令牌配额预扣结算 · RPM 可配置",
                "built": True,
            },
        ],
        "alerts": [
            {
                "cat": "security",
                "type": "注入",
                "level": "warn",
                "summary": "prod-dify 今日拦截 3 次注入尝试",
                "payload": None,
            }
        ],
    }


def _traffic_payload(rows: list[dict[str, Any]], window: str | None, ctx: str | None) -> dict[str, Any]:
    filtered = rows
    if window in {"1h", "24h", "7d"}:
        horizon = {"1h": timedelta(hours=1), "24h": timedelta(days=1), "7d": timedelta(days=7)}[window]
        start = datetime.now(timezone.utc) - horizon
        filtered = [row for row in filtered if (ts := _parse_timestamp(row.get("timestamp"))) is None or ts >= start]
    if ctx in {"dev", "prod"}:
        filtered = [row for row in filtered if _row_ctx(row) == ctx]

    if filtered:
        upstreams = []
        seen: set[tuple[str, str]] = set()
        for row in filtered:
            key = (str(row.get("actor_model_id", "unknown")), _row_ctx(row))
            if key in seen:
                continue
            seen.add(key)
            upstreams.append({"name": key[0], "ctx": key[1], "rate": max(1, sum(1 for item in filtered if (str(item.get("actor_model_id", "")), _row_ctx(item)) == key))})
        upstreams = upstreams[:2]
    else:
        upstreams = [
            {"name": "Dify RAG", "ctx": "prod", "rate": 1200},
            {"name": "本地批处理", "ctx": "dev", "rate": 180},
        ]

    return {
        "inbound": {
            "upstreams": upstreams,
            "gate": {
                "hit": len(filtered) * 3,
                "blocked": sum(1 for row in filtered if _row_status(row) in {"red", "yellow"}),
                "passed": len(filtered) * 10,
            },
            "downstream": [{"name": "私有 Qwen", "note": "脱敏后"}],
        },
        "outbound": {
            "built": False,
            "note": "出站安全网关已上线（有害 / PHI 回流 / 幻觉规则检查）；实时响应流可视化即将推出",
            "gate": {"phi_reflow": 0, "harmful": 0, "hallucination": 0},
        },
    }


def _events_payload(rows: list[dict[str, Any]], cat: str | None, ctx: str | None, limit: int | None) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for row in rows:
        if cat in {"comp", "sec"} and _row_cat(row) != cat:
            continue
        if ctx in {"dev", "prod"} and _row_ctx(row) != ctx:
            continue
        event: dict[str, Any] = {
            "ts": (_parse_timestamp(row.get("timestamp")) or datetime(2026, 5, 29, 8, 12, 3, tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cat": _row_cat(row),
            "status": _row_status(row),
            "upstream": str(row.get("actor_model_id") or row.get("action_tool") or "unknown"),
            "ctx": _row_ctx(row),
            "action": str(row.get("result_reason") or row.get("action_operation") or "聚合"),
            "ref": _row_ref(row),
        }
        if event["cat"] == "sec":
            event["sec_type"] = "注入" if "injection" in str(row.get("action_tool", "")).lower() else "滥用"
            event["payload"] = None
        else:
            event["level"] = _row_level(row)
        events.append(event)
        if limit is not None and len(events) >= limit:
            break
    if not events:
        events = [
            {
                "ts": "2026-05-29T08:12:03Z",
                "cat": "comp",
                "status": "green",
                "upstream": "dify-rag",
                "ctx": "prod",
                "level": "L3",
                "action": "脱敏后路由 qwen-max",
                "ref": "routing#a1b2",
            },
            {
                "ts": "2026-05-29T08:15:41Z",
                "cat": "sec",
                "status": "red",
                "upstream": "dify-rag",
                "ctx": "prod",
                "sec_type": "注入",
                "action": "检索内容含可疑指令→隔离",
                "ref": "inj#c3d4",
                "payload": None,
            },
        ]
        if limit is not None:
            events = events[:limit]
    return {"events": events}


app = _app_factory()


def _degraded_response() -> Any:
    return _response(
        {"status": "degraded", "error": {"code": "data_source_unavailable", "msg": "data source unavailable"}},
        503,
    )


def _generic_error_response() -> Any:
    return _response({"error": {"code": "data_source_unavailable", "msg": "data source unavailable"}}, 500)


@app.get(f"{API_BASE}/posture")
def posture() -> Any:
    try:
        payload = serialize_posture(_posture_payload(_audit_rows()))
        return assert_no_phi(payload, "GET /posture")
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/traffic")
def traffic(window: str | None = Query(default=None), ctx: str | None = Query(default=None)) -> Any:
    try:
        payload = serialize_traffic(_traffic_payload(_audit_rows(), window, ctx))
        return assert_no_phi(payload, "GET /traffic")
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/events")
def events(
    cat: str | None = Query(default=None),
    ctx: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> Any:
    try:
        payload = serialize_events(_events_payload(_audit_rows(limit), cat, ctx, limit))
        return assert_no_phi(payload, "GET /events")
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/audit/{{ref}}")
def audit(ref: str) -> Any:
    try:
        row = _audit_row_by_ref(ref)
        if row is None:
            return _response({"error": {"code": "not_found", "msg": "data source unavailable"}}, 404)
        return serialize_audit_lineage(_audit_lineage_payload(row))
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/upstreams")
def upstreams() -> Any:
    try:
        rows = _audit_rows(limit=1)
        if rows:
            summary: dict[tuple[str, str], dict[str, Any]] = {}
            for row in rows:
                key = (str(row.get("actor_model_id", "unknown")), _row_ctx(row))
                item = summary.setdefault(
                    key,
                    {
                        "name": key[0],
                        "ctx": key[1],
                        "protocol": "openai",
                        "status": _row_status(row),
                        "traffic_today": 0,
                        "phi": "命中 0 / 拦 0",
                    },
                )
                item["traffic_today"] += 1
                item["status"] = _row_status(row)
                item["phi"] = "命中 312 / 拦 5" if item["ctx"] == "prod" else "命中 0 / 拦 0"
            payload = {"upstreams": list(summary.values())}
        else:
            payload = {
                "upstreams": [
                    {"name": "prod-dify-rag", "ctx": "prod", "protocol": "openai", "status": "green", "traffic_today": 8247, "phi": "命中 312 / 拦 5"},
                    {"name": "dev-local-batch", "ctx": "dev", "protocol": "openai", "status": "green", "traffic_today": 1203, "phi": "命中 0 / 拦 0"},
                ]
            }
        return serialize_upstreams(payload)
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/config/{{section}}")
def config(section: str) -> Any:
    try:
        _audit_rows(limit=1)
        payload = _config_snapshot_payload(section)
        if payload is None:
            return _response({"error": {"code": "not_found", "msg": "data source unavailable"}}, 404)
        return serialize_config_snapshot(payload)
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/cost")
def cost() -> Any:
    try:
        _audit_rows(limit=1)
        return serialize_cost(_cost_payload())
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/channels")
def channels() -> Any:
    try:
        _audit_rows(limit=1)
        return serialize_channels(_channels_payload())
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/admin/users")
def admin_users() -> Any:
    try:
        _audit_rows(limit=1)
        status, parsed = _new_api_admin_request("GET", "/api/user/?p=1&page_size=100")
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return serialize_admin_users(_live_items_payload(parsed, "users"))
    except ClickHouseUnavailable:
        return _degraded_response()
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/admin/tokens")
def admin_tokens() -> Any:
    try:
        _audit_rows(limit=1)
        status, parsed = _new_api_admin_request("GET", "/api/token/?p=1&page_size=100")
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return serialize_admin_tokens_mgmt(_live_items_payload(parsed, "tokens"))
    except ClickHouseUnavailable:
        return _degraded_response()
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/admin/channels")
def admin_channels() -> Any:
    try:
        _audit_rows(limit=1)
        status, parsed = _new_api_admin_request("GET", "/api/channel/?p=1&page_size=100")
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return serialize_admin_channels_mgmt(_live_items_payload(parsed, "channels"))
    except ClickHouseUnavailable:
        return _degraded_response()
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/audit/export")
def audit_export(
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
    scope: str | None = Query(default=None),
    change_id: str | None = Query(default=None),
    window: str | None = Query(default=None),
) -> Any:
    try:
        body = payload or {}
        if body.get("scope") is not None:
            scope = str(body.get("scope"))
        if body.get("change_id") is not None:
            change_id = str(body.get("change_id"))
        if body.get("window") is not None:
            window = str(body.get("window"))
        _append_audit_event(
            _audit_event_for_operation(
                "audit-export",
                "export",
                "success",
                "AUDIT bundle exported",
                change_id=change_id,
                scope=scope,
                window=window,
            )
        )
        return serialize_audit_export(_audit_export_payload(scope, change_id, window))
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/config/{{section}}/propose")
def config_propose(
    section: str,
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    try:
        _audit_rows(limit=1)
        if section not in _ALLOWED_CONFIG_SECTIONS:
            return _response({"error": {"code": "not_found", "msg": "data source unavailable"}}, 404)
        return serialize_config_propose(_config_propose_payload(section, payload))
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


def _console_role_from_new_api(role: Any) -> str:
    """Map a new-api role int (1 common / 10 admin / 100 root) to a Console role."""
    try:
        role_int = int(role)
    except (TypeError, ValueError):
        role_int = 0
    return "sysadmin" if role_int >= 10 else "rdlead"


@app.post(f"{API_BASE}/auth/login")
def auth_login(payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT) -> Any:
    body = payload or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username or not password:
        return _response({"error": {"code": "invalid_params", "msg": "用户名或密码不能为空"}}, 400)
    try:
        result = _new_api_login(username, password)
    except Exception:
        # new-api unreachable / malformed: fail closed, never leak the cause.
        return _response({"error": {"code": "upstream_unavailable", "msg": "登录服务暂不可用"}}, 502)
    if not result.get("success"):
        # 200 + success:false == bad credentials; never echo new-api's message.
        return _response({"error": {"code": "unauthorized", "msg": "用户名或密码错误"}}, 401)
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if data.get("require_2fa"):
        return _response(
            {"error": {"code": "twofa_unsupported", "msg": "该账号启用了两步验证，请在 new-api 后台登录"}},
            400,
        )
    console_role = _console_role_from_new_api(data.get("role"))
    resolved_username = str(data.get("username") or username)
    response: dict[str, Any] = {
        "ok": True,
        "role": console_role,
        "username": resolved_username,
        "display_name": str(data.get("display_name") or ""),
    }
    # Mint a session token so the browser can persist the login across refreshes and
    # authorize admin-write calls. Tolerant: if A0_SESSION_SECRET is unset the login
    # still succeeds (no token) — only the persistence/write features need it.
    if _session_secret():
        # Never fail the login itself on a token-mint hiccup — the session is additive.
        with contextlib.suppress(Exception):
            response["token"] = _mint_session(
                data.get("id"), resolved_username, console_role, data.get("role")
            )
    return response


# ── A0 user-management write proxies (sysadmin-only; replayed to new-api) ─────────
# These POST-shaped endpoints let a Console sysadmin manage new-api users without
# ever touching the new-api admin token in the browser. Every handler: (1) gates on
# a sysadmin session, (2) requires the server-held admin token, (3) validates input
# locally — A0 NEVER creates a root (role=100) — (4) for role/delete enforces the
# new-api role hierarchy (cannot act on a peer/superior), (5) maps any new-api
# business failure to a GENERIC 4xx (new-api's message is never echoed). The admin
# token and operator passwords are never logged.
_MGMT_USERNAME_RE = re.compile(r"^[\w.-]{1,20}$")
_MGMT_GROUP_RE = re.compile(r"^[\w-]{1,64}$")
_MGMT_ALLOWED_ROLES = {1, 10}  # common / admin — root (100) is never minted by A0
_MGMT_NAME_MAX = 80
_MGMT_ALLOWED_LEVELS = {"L2", "L3", "L4"}
_MGMT_ALLOWED_CHANNEL_CREATE_FIELDS = {"name", "type", "key", "base_url", "models", "group", "weight"}
_MGMT_ALLOWED_CHANNEL_FIELDS = {"name", "type", "key", "base_url", "models", "group", "weight", "status"}
_MGMT_ALLOWED_TOKEN_CREATE_FIELDS = {
    "name",
    "remain_quota",
    "unlimited_quota",
    "group",
    "allowed_data_levels",
    "expired_time",
}
_MGMT_ALLOWED_TOKEN_FIELDS = {
    "name",
    "status",
    "remain_quota",
    "unlimited_quota",
    "group",
    "allowed_data_levels",
    "expired_time",
}


def _forbidden_response(claims: dict[str, Any] | None) -> Any:
    """401 when there is no valid session; 403 when valid but not sysadmin."""
    if claims is None:
        return _response({"error": {"code": "unauthorized", "msg": "登录态无效或已过期"}}, 401)
    return _response({"error": {"code": "forbidden", "msg": "需要系统管理员权限"}}, 403)


def _sysadmin_or_error(authorization: str | None) -> tuple[dict[str, Any] | None, Any]:
    """Resolve a sysadmin session, else return (None, error-response)."""
    session = _require_session(authorization)
    if session is None or session.get("cr") != "sysadmin":
        return None, _forbidden_response(session)
    try:
        headers = _new_api_admin_headers()
    except NewApiUnavailable:
        headers = None
    if headers is None:
        return None, _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    return session, None


def _operation_failed_response() -> Any:
    """Generic admin-write failure — never echoes new-api's own message."""
    return _response({"error": {"code": "operation_failed", "msg": "操作失败"}}, 422)


def _invalid_params_response() -> Any:
    return _response({"error": {"code": "invalid_params", "msg": "参数不合法"}}, 400)


def _admin_write_succeeded(status: int, parsed: dict[str, Any]) -> bool:
    return 200 <= status < 300 and bool(parsed.get("success", True))


def _live_items_payload(parsed: dict[str, Any], key: str) -> dict[str, Any]:
    data = parsed.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return {key: data["items"]}
        if isinstance(data.get(key), list):
            return {key: data[key]}
    if isinstance(data, list):
        return {key: data}
    return {key: []}


def _is_valid_name(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and len(text) <= _MGMT_NAME_MAX and all(ch >= " " for ch in text)


def _validate_group(value: Any) -> str | None:
    group = str(value or "").strip()
    if not group or not _MGMT_GROUP_RE.fullmatch(group):
        return None
    return group


def _validate_models(value: Any) -> list[str] | str | None:
    if isinstance(value, list):
        models = [str(item).strip() for item in value if str(item).strip()]
        return models or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _validate_base_url(value: Any) -> str | None:
    url = str(value or "").strip()
    if not url or len(url) > 2048:
        return None
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _validate_quota(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text) if "." in text else int(text)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _validate_data_levels(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    levels: list[str] = []
    for item in value:
        level = str(item)
        if level not in _MGMT_ALLOWED_LEVELS:
            return None
        if level not in levels:
            levels.append(level)
    return levels or None


# new-api channel types are ints (constant/channel.go). The Console "类型" field is a
# free-text provider name, so A0 (the type adapter) maps a name → int, and also accepts
# a raw int / numeric string (used by the medical channel templates). Unknown → reject.
_CHANNEL_TYPE_NAME_TO_INT = {
    "openai": 1,
    "azure": 3,
    "ollama": 4,
    "custom": 8,
    "openai-compatible": 8,
    "anthropic": 14,
    "claude": 14,
    "baidu": 15,
    "zhipu": 16,
    "ali": 17,
    "qwen": 17,
    "dashscope": 17,
    "openrouter": 20,
    "gemini": 24,
    "google": 24,
    "moonshot": 25,
    "perplexity": 27,
    "aws": 33,
    "bedrock": 33,
    "cohere": 34,
    "minimax": 35,
    "dify": 37,
    "siliconflow": 40,
    "vertex": 41,
    "vertexai": 41,
    "mistral": 42,
    "deepseek": 43,
    "volcengine": 45,
    "doubao": 45,
    "xinference": 47,
    "vllm": 47,
    "xai": 48,
    "grok": 48,
}


def _validate_channel_type(value: Any) -> int | None:
    """Resolve a new-api channel type int from a provider name, int, or numeric string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        n = int(text)
        return n if n > 0 else None
    return _CHANNEL_TYPE_NAME_TO_INT.get(text.lower())


def _models_csv(models: Any) -> str:
    """new-api Channel.Models is a comma-separated string; flatten a list/str to that."""
    if isinstance(models, list):
        return ",".join(str(m).strip() for m in models if str(m).strip())
    return str(models).strip()


def _validated_channel_create(body: dict[str, Any]) -> dict[str, Any] | None:
    if set(body) - _MGMT_ALLOWED_CHANNEL_CREATE_FIELDS:
        return None
    name = str(body.get("name") or "").strip()
    channel_type = _validate_channel_type(body.get("type"))
    secret = str(body.get("key") or "").strip()
    models = _validate_models(body.get("models"))
    group = _validate_group(body.get("group"))
    weight = _coerce_int(body.get("weight"), -1)
    if not _is_valid_name(name) or channel_type is None or not secret or models is None or group is None:
        return None
    if weight < 0 or weight > 100:
        return None
    out: dict[str, Any] = {
        "name": name,
        "type": channel_type,
        "key": secret,
        "models": _models_csv(models),
        "group": group,
        "weight": weight,
    }
    if body.get("base_url") is not None:
        base_url = _validate_base_url(body.get("base_url"))
        if base_url is None:
            return None
        out["base_url"] = base_url
    return out


def _validated_channel_update(channel_id: int, body: dict[str, Any]) -> dict[str, Any] | None:
    update: dict[str, Any] = {"id": channel_id}
    for key, value in body.items():
        if key not in _MGMT_ALLOWED_CHANNEL_FIELDS:
            return None
        if key == "name":
            if not _is_valid_name(value):
                return None
            update[key] = str(value).strip()
        elif key == "key":
            secret = str(value or "").strip()
            if not secret:
                return None
            update[key] = secret
        elif key == "base_url":
            base_url = _validate_base_url(value)
            if base_url is None:
                return None
            update[key] = base_url
        elif key == "models":
            models = _validate_models(value)
            if models is None:
                return None
            update[key] = _models_csv(models)
        elif key == "type":
            channel_type = _validate_channel_type(value)
            if channel_type is None:
                return None
            update[key] = channel_type
        elif key == "group":
            group = _validate_group(value)
            if group is None:
                return None
            update[key] = group
        elif key == "weight":
            weight = _coerce_int(value, -1)
            if weight < 0 or weight > 100:
                return None
            update[key] = weight
        else:
            update[key] = value
    return update if len(update) > 1 else None


def _validated_token_create(body: dict[str, Any]) -> dict[str, Any] | None:
    if set(body) - _MGMT_ALLOWED_TOKEN_CREATE_FIELDS:
        return None
    name = str(body.get("name") or "").strip()
    group = _validate_group(body.get("group"))
    levels = _validate_data_levels(body.get("allowed_data_levels"))
    unlimited = bool(body.get("unlimited_quota"))
    quota = _validate_quota(body.get("remain_quota")) if body.get("remain_quota") is not None else None
    if not _is_valid_name(name) or group is None or levels is None:
        return None
    if not unlimited and quota is None:
        return None
    out: dict[str, Any] = {"name": name, "group": group, "allowed_data_levels": levels}
    if body.get("unlimited_quota") is not None:
        out["unlimited_quota"] = unlimited
    if quota is not None:
        out["remain_quota"] = quota
    if body.get("expired_time") is not None:
        out["expired_time"] = body.get("expired_time")
    return out


def _validated_token_update(token_id: int, body: dict[str, Any]) -> dict[str, Any] | None:
    update: dict[str, Any] = {"id": token_id}
    for key, value in body.items():
        if key not in _MGMT_ALLOWED_TOKEN_FIELDS:
            return None
        if key == "name":
            if not _is_valid_name(value):
                return None
            update[key] = str(value).strip()
        elif key == "group":
            group = _validate_group(value)
            if group is None:
                return None
            update[key] = group
        elif key == "allowed_data_levels":
            levels = _validate_data_levels(value)
            if levels is None:
                return None
            update[key] = levels
        elif key == "remain_quota":
            quota = _validate_quota(value)
            if quota is None:
                return None
            update[key] = quota
        elif key == "unlimited_quota":
            if not isinstance(value, bool):
                return None
            update[key] = value
        elif key == "status":
            if value not in ("enabled", "disabled"):
                return None
            update[key] = value
        elif key == "expired_time":
            # The mgmt serializer emits expired_time as a display string (e.g. "-1"),
            # and the Console round-trips it verbatim. new-api's Token.ExpiredTime is an
            # int64, so a string body would fail ShouldBindJSON — A0 (the type adapter)
            # coerces here, mirroring how _validate_quota accepts numeric strings.
            try:
                update[key] = int(value)
            except (TypeError, ValueError):
                return None
        else:
            update[key] = value
    return update if len(update) > 1 else None


# new-api TokenStatus ints (common/constants.go): 1=enabled, 2=disabled.
_TOKEN_STATUS_TO_INT = {"enabled": 1, "disabled": 2}

# Native new-api Token fields that UpdateToken (controller/token.go) overwrites from
# the request body on a non-status_only PUT. A partial body therefore BLANKS every
# omitted field (name/group/expiry → ""), so a quota/levels edit must round-trip the
# full object. These are exactly the fields the `else` branch of UpdateToken copies.
_TOKEN_NATIVE_UPDATE_FIELDS = (
    "name",
    "group",
    "expired_time",
    "remain_quota",
    "unlimited_quota",
    "model_limits_enabled",
    "model_limits",
    "allow_ips",
    "cross_group_retry",
)


def _merge_token_update(target_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
    """Read-modify-write for new-api's full-overwrite UpdateToken.

    new-api's PUT /api/token/ replaces EVERY native field from the bound JSON, so a
    partial body (e.g. just remain_quota) silently wipes name/group/expiry. We fetch
    the current token, carry every native field forward, and overlay only the validated
    change — so a quota edit changes the quota and nothing else. Returns None if the
    current token can't be read (caller maps that to a generic operation failure).
    """
    status, parsed = _new_api_admin_request("GET", f"/api/token/{target_id}")
    if not _admin_write_succeeded(status, parsed):
        return None
    current = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(current, dict):
        return None
    merged: dict[str, Any] = {"id": target_id}
    for field in _TOKEN_NATIVE_UPDATE_FIELDS:
        if field in current:
            merged[field] = current[field]
    for key, value in changes.items():
        if key in ("id", "status"):
            continue  # id is fixed; status goes through the status_only path
        if key == "allowed_data_levels":
            # new-api has no such column — the Console derives the level heuristically
            # from group/model_limits, so there is nothing to persist upstream here.
            continue
        merged[key] = value
    return merged


def _new_api_user_role(user_id: int) -> int | None:
    """Return the target user's current new-api role int, or None if not found."""
    status, parsed = _new_api_admin_request("GET", "/api/user/?p=1&page_size=100")
    if not _admin_write_succeeded(status, parsed):
        return None
    data = parsed.get("data")
    items = data.get("items") if isinstance(data, dict) else data
    for user in items or []:
        if isinstance(user, dict) and _coerce_int(user.get("id"), -1) == user_id:
            return _coerce_int(user.get("role"))
    return None


def _can_manage_target(operator_role: int, target_role: int) -> bool:
    """Mirror new-api canManageTargetRole: act only on a strictly-lower role."""
    return target_role < operator_role


@app.get(f"{API_BASE}/admin/users/manage_list")
def admin_users_manage_list(authorization: str | None = Header(default=None)) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    try:
        status, parsed = _new_api_admin_request("GET", "/api/user/?p=1&page_size=100")
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return serialize_admin_users_mgmt(parsed.get("data") or {})
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/users")
def admin_users_create(
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    body = payload or {}
    username = str(body.get("username") or "")
    password = str(body.get("password") or "")
    display_name = str(body.get("display_name") or "")
    role = _coerce_int(body.get("role"), 1) if body.get("role") is not None else 1
    group = body.get("group")
    if not _MGMT_USERNAME_RE.fullmatch(username):
        return _invalid_params_response()
    if not 8 <= len(password) <= 20:
        return _invalid_params_response()
    if role not in _MGMT_ALLOWED_ROLES:
        return _invalid_params_response()
    if group is not None and not _MGMT_GROUP_RE.fullmatch(str(group)):
        return _invalid_params_response()
    # An operator may not mint a role >= their own (so an admin can't clone an admin).
    if not _can_manage_target(_coerce_int(session.get("nr")), role):
        return _forbidden_response(session)
    request_body: dict[str, Any] = {
        "username": username,
        "password": password,
        "display_name": display_name,
        "role": role,
    }
    if group is not None:
        request_body["group"] = str(group)
    try:
        status, parsed = _new_api_admin_request("POST", "/api/user/", request_body)
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/users/{{user_id}}/update")
def admin_users_update(
    user_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(user_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    body = payload or {}
    update: dict[str, Any] = {"id": target_id}
    if body.get("username") is not None:
        username = str(body.get("username"))
        if not _MGMT_USERNAME_RE.fullmatch(username):
            return _invalid_params_response()
        update["username"] = username
    if body.get("display_name") is not None:
        update["display_name"] = str(body.get("display_name"))
    if body.get("group") is not None:
        group = str(body.get("group"))
        if not _MGMT_GROUP_RE.fullmatch(group):
            return _invalid_params_response()
        update["group"] = group
    role_changed = body.get("role") is not None
    if role_changed:
        role = _coerce_int(body.get("role"), -1)
        if role not in _MGMT_ALLOWED_ROLES:
            return _invalid_params_response()
        update["role"] = role
    try:
        # A role change is privileged: the operator must out-rank BOTH the target's
        # current role and the requested new role (mirror new-api canManageTargetRole).
        if role_changed:
            current = _new_api_user_role(target_id)
            if current is None:
                return _operation_failed_response()
            operator = _coerce_int(session.get("nr"))
            if not _can_manage_target(operator, current) or not _can_manage_target(
                operator, _coerce_int(update["role"])
            ):
                return _forbidden_response(session)
        status, parsed = _new_api_admin_request("PUT", "/api/user/", update)
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/users/{{user_id}}/password")
def admin_users_password(
    user_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(user_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    password = str((payload or {}).get("password") or "")
    if not 8 <= len(password) <= 20:
        return _invalid_params_response()
    try:
        status, parsed = _new_api_admin_request(
            "PUT", "/api/user/", {"id": target_id, "password": password}
        )
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/users/{{user_id}}/status")
def admin_users_status(
    user_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(user_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    body = payload or {}
    if "enabled" not in body or not isinstance(body.get("enabled"), bool):
        return _invalid_params_response()
    action = "enable" if body.get("enabled") else "disable"
    try:
        status, parsed = _new_api_admin_request(
            "POST", "/api/user/manage", {"id": target_id, "action": action}
        )
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/users/{{user_id}}/role")
def admin_users_role(
    user_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(user_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    action = str((payload or {}).get("action") or "")
    if action not in {"promote", "demote"}:
        return _invalid_params_response()
    try:
        # Changing a target's role is privileged: the operator must strictly out-rank
        # the target's CURRENT role (mirror new-api canManageTargetRole).
        current = _new_api_user_role(target_id)
        if current is None:
            return _operation_failed_response()
        if not _can_manage_target(_coerce_int(session.get("nr")), current):
            return _forbidden_response(session)
        status, parsed = _new_api_admin_request(
            "POST", "/api/user/manage", {"id": target_id, "action": action}
        )
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/users/{{user_id}}/delete")
def admin_users_delete(
    user_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(user_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    try:
        # Deleting a target is privileged: the operator must strictly out-rank the
        # target's CURRENT role (mirror new-api canManageTargetRole).
        current = _new_api_user_role(target_id)
        if current is None:
            return _operation_failed_response()
        if not _can_manage_target(_coerce_int(session.get("nr")), current):
            return _forbidden_response(session)
        status, parsed = _new_api_admin_request(
            "POST", "/api/user/manage", {"id": target_id, "action": "delete"}
        )
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/channels")
def admin_channels_create(
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    request_body = _validated_channel_create(payload or {})
    if request_body is None:
        return _invalid_params_response()
    try:
        # new-api AddChannel binds {mode, channel:{...}}; a bare flat channel makes
        # it nil-deref/panic (HTTP 500). Wrap as a single-channel add.
        wrapped = {"mode": "single", "channel": request_body}
        status, parsed = _new_api_admin_request("POST", "/api/channel/", wrapped)
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/channels/{{channel_id}}/update")
def admin_channels_update(
    channel_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(channel_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    request_body = _validated_channel_update(target_id, payload or {})
    if request_body is None:
        return _invalid_params_response()
    try:
        status, parsed = _new_api_admin_request("PUT", "/api/channel/", request_body)
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/channels/{{channel_id}}/delete")
def admin_channels_delete(
    channel_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(channel_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    try:
        status, parsed = _new_api_admin_request("DELETE", f"/api/channel/{target_id}")
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/channels/{{channel_id}}/test")
def admin_channels_test(
    channel_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(channel_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    try:
        status, parsed = _new_api_admin_request("GET", f"/api/channel/test/{target_id}")
        # A reachable-or-not verdict is a RESULT, not an operation failure: the probe ran.
        # Only a transport/HTTP failure (new-api itself unreachable) is an operation error
        # — otherwise a not-yet-configured channel (e.g. a medical template with a blank
        # key) would falsely read as "操作失败". Never echo new-api's message (it can carry
        # the upstream base_url / provider error → would breach the 0-leak boundary).
        if status != 200 or not isinstance(parsed, dict):
            return _operation_failed_response()
        reachable = bool(parsed.get("success"))
        latency_ms: int | None = None
        raw_time = parsed.get("time")
        if isinstance(raw_time, (int, float)) and raw_time >= 0:
            latency_ms = int(round(raw_time * 1000))
        return {"ok": True, "reachable": reachable, "latency_ms": latency_ms}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/tokens")
def admin_tokens_create(
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    request_body = _validated_token_create(payload or {})
    if request_body is None:
        return _invalid_params_response()
    try:
        status, parsed = _new_api_admin_request("POST", "/api/token/", request_body)
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/tokens/{{token_id}}/update")
def admin_tokens_update(
    token_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(token_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    changes = _validated_token_update(target_id, payload or {})
    if changes is None:
        return _invalid_params_response()
    try:
        change_keys = set(changes) - {"id"}
        # Status toggles ride new-api's status_only path, which touches ONLY the status
        # column and leaves name/group/quota intact (the int status also avoids the
        # string→int bind error a plain PUT would hit).
        if change_keys == {"status"}:
            status_int = _TOKEN_STATUS_TO_INT.get(changes["status"])
            if status_int is None:
                return _invalid_params_response()
            status, parsed = _new_api_admin_request(
                "PUT", "/api/token/?status_only=1", {"id": target_id, "status": status_int}
            )
            if not _admin_write_succeeded(status, parsed):
                return _operation_failed_response()
            return {"ok": True}
        # Quota / levels / name / group edits: read-modify-write so new-api's
        # full-overwrite UpdateToken cannot blank the fields we did not touch.
        merged = _merge_token_update(target_id, changes)
        if merged is None:
            return _operation_failed_response()
        status, parsed = _new_api_admin_request("PUT", "/api/token/", merged)
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.post(f"{API_BASE}/admin/tokens/{{token_id}}/delete")
def admin_tokens_delete(
    token_id: str,
    authorization: str | None = Header(default=None),
    payload: dict[str, Any] | None = REQUEST_BODY_DEFAULT,
) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    target_id = _coerce_int(token_id, -1)
    if target_id < 0:
        return _invalid_params_response()
    try:
        status, parsed = _new_api_admin_request("DELETE", f"/api/token/{target_id}")
        if not _admin_write_succeeded(status, parsed):
            return _operation_failed_response()
        return {"ok": True}
    except NewApiUnavailable:
        return _response(
            {"error": {"code": "upstream_unavailable", "msg": "管理服务暂不可用"}}, 502
        )
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/admin/groups")
def admin_groups(authorization: str | None = Header(default=None)) -> Any:
    session, error_response = _sysadmin_or_error(authorization)
    if session is None:
        return error_response
    # new-api group listing is self-scoped; A0 keeps this minimal and static so the
    # management form has a stable, non-PHI group source.
    return {"groups": ["default"]}


@app.get("/health")
def health() -> Any:
    return {"status": "ok", "service": "a0-api", "version": CONTRACT_VERSION}


def main() -> int:
    if FastAPI is None:
        print(
            json.dumps(
                {"status": "error", "msg": "fastapi dependency unavailable"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    import uvicorn

    uvicorn.run(app, host=DEFAULT_HTTP_HOST, port=DEFAULT_HTTP_PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
