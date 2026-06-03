from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any
from urllib import error, parse, request

from serializers import (
    assert_no_phi,
    serialize_admin_channels,
    serialize_admin_tokens,
    serialize_admin_users,
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
    JSONResponse = import_module("fastapi.responses").JSONResponse  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - local test fallback or partial namespace package
    FastAPI = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

    def Body(default: Any = None, **_: Any) -> Any:
        return default

    def Query(default: Any = None, **_: Any) -> Any:
        return default

API_BASE = "/api/v1"
CONTRACT_VERSION = "0.7.1"
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
    ) -> _LocalResponse:
        params = params or {}
        route_path = path.split("?", 1)[0]
        handler, route_params = self._match_route(method.upper(), route_path)
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
        if route_path.startswith(f"{API_BASE}/audit/") and method.upper() == "GET":
            ref = route_params.get("ref", "")
            return _normalize_local_response(handler(ref=ref))
        if route_path.startswith(f"{API_BASE}/config/") and route_path.endswith("/propose") and method.upper() == "POST":
            section = route_params.get("section", "")
            payload = json if json is not None else data
            return _normalize_local_response(handler(section=section, payload=payload))
        if route_path.startswith(f"{API_BASE}/config/") and method.upper() == "GET":
            section = route_params.get("section", "")
            return _normalize_local_response(handler(section=section))
        if route_path == f"{API_BASE}/audit/export" and method.upper() == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(payload=payload))
        if route_path == f"{API_BASE}/auth/login" and method.upper() == "POST":
            payload = json if json is not None else data
            return _normalize_local_response(handler(payload=payload))
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
            def get(self, url: str, params: dict[str, Any] | None = None) -> _LocalResponse:
                return app_obj.request("GET", url, params=params)

            def post(
                self,
                url: str,
                params: dict[str, Any] | None = None,
                json: Any | None = None,
                data: Any | None = None,
            ) -> _LocalResponse:
                return app_obj.request("POST", url, params=params, json=json, data=data)

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
            "built": False,
            "note": "🚧 v0.6 规划",
            "fields": [{"k": "PHI 回流", "v": "拦截（规划）"}, {"k": "幻觉医嘱", "v": "告警（规划）"}],
        },
        "quota": {
            "section": "quota",
            "title": "配额限流",
            "built": False,
            "note": "🚧 v0.6 规划",
            "fields": [{"k": "按上游", "v": "规划"}, {"k": "日成本护栏", "v": "规划"}],
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


def _cost_payload() -> dict[str, Any]:
    return {
        "window": "month",
        "kpi": {
            "month_cost": "¥3,240",
            "saved_vs_direct": "¥2,240",
            "saved_ratio": "41%",
            "cache_hit_ratio": "28%",
            "cache_saved": "¥420",
            "cap_day": "¥200",
            "cap_used": "¥124",
            "cap_left_ratio": "62%",
            "normal_lane_ratio": "73%",
        },
        "by_lane": [
            {"name": "常规通道（低成本池）", "color_token": "lane-normal", "pct": 36, "amount": "¥1,180"},
            {"name": "敏感通道（私有）", "color_token": "lane-sensitive", "pct": 64, "amount": "¥2,060"},
        ],
        "by_model": [
            {"name": "qwen-max-2026", "color_token": "compliance", "pct": 43, "amount": "¥1,400"},
            {"name": "claude-sonnet", "color_token": "primary", "pct": 28, "amount": "¥900"},
            {"name": "deepseek-v4-pro", "color_token": "ok", "pct": 17, "amount": "¥540"},
            {"name": "qwen-vl-2026", "color_token": "cost", "pct": 12, "amount": "¥400"},
        ],
        "trend": [58, 62, 55, 70, 64, 61, 52],
        "tips": [
            {"tip": "开发期简单补全占 38%，建议默认走 deepseek（更省的小模型）", "saving": "省 ¥18/天"},
            {"tip": "常规通道缓存命中 28%，规范调用模板可提到 ~40%", "saving": "省 ¥260/月"},
            {"tip": "claude-sonnet 28% 调用可降级到 qwen-max（境内）", "saving": "省 ¥420/月"},
        ],
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
                "status": "planned",
                "metric": "🚧 v0.6",
                "built": False,
            },
            {
                "id": "rate-limit",
                "group": "security",
                "status": "planned",
                "metric": "🚧 v0.6",
                "built": False,
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
            "note": "🚧 v0.6 规划",
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
        return serialize_admin_users(_admin_users_payload())
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/admin/tokens")
def admin_tokens() -> Any:
    try:
        _audit_rows(limit=1)
        return serialize_admin_tokens(_admin_tokens_payload())
    except ClickHouseUnavailable:
        return _degraded_response()
    except Exception:
        return _generic_error_response()


@app.get(f"{API_BASE}/admin/channels")
def admin_channels() -> Any:
    try:
        _audit_rows(limit=1)
        return serialize_admin_channels(_admin_channels_payload())
    except ClickHouseUnavailable:
        return _degraded_response()
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
    return {
        "ok": True,
        "role": _console_role_from_new_api(data.get("role")),
        "username": str(data.get("username") or username),
        "display_name": str(data.get("display_name") or ""),
    }


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
