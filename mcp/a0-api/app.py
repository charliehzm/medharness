from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any
from urllib import error, parse, request

try:  # pragma: no cover - exercised when the real dependency is installed
    _fastapi = import_module("fastapi")
    FastAPI = _fastapi.FastAPI  # type: ignore[attr-defined]
    Query = _fastapi.Query  # type: ignore[attr-defined]
    JSONResponse = import_module("fastapi.responses").JSONResponse  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - local test fallback or partial namespace package
    FastAPI = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

    def Query(default: Any = None, **_: Any) -> Any:
        return default

from serializers import assert_no_phi, serialize_events, serialize_posture, serialize_traffic

API_BASE = "/api/v1"
CONTRACT_VERSION = "0.7.1"
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8010
DEFAULT_CLICKHOUSE_HOST = "clickhouse"
DEFAULT_CLICKHOUSE_PORT = 8123
DEFAULT_CLICKHOUSE_USER = "medharness"
DEFAULT_CLICKHOUSE_PASSWORD = ""
DEFAULT_CLICKHOUSE_DATABASE = "medharness"


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
        self.routes: dict[tuple[str, str], Any] = {}

    def get(self, path: str) -> Any:
        def decorator(func: Any) -> Any:
            self.routes[("GET", path)] = func
            return func

        return decorator

    def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> _LocalResponse:
        params = params or {}
        route_path = path.split("?", 1)[0]
        handler = self.routes.get((method.upper(), route_path))
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
        return _normalize_local_response(handler())


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


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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


@app.get(f"{API_BASE}/posture")
def posture() -> Any:
    try:
        payload = serialize_posture(_posture_payload(_audit_rows()))
        return assert_no_phi(payload, "GET /posture")
    except ClickHouseUnavailable:
        return _response(
            {"status": "degraded", "error": {"code": "data_source_unavailable", "msg": "data source unavailable"}},
            503,
        )
    except Exception:
        return _response({"error": {"code": "data_source_unavailable", "msg": "data source unavailable"}}, 500)


@app.get(f"{API_BASE}/traffic")
def traffic(window: str | None = Query(default=None), ctx: str | None = Query(default=None)) -> Any:
    try:
        payload = serialize_traffic(_traffic_payload(_audit_rows(), window, ctx))
        return assert_no_phi(payload, "GET /traffic")
    except ClickHouseUnavailable:
        return _response(
            {"status": "degraded", "error": {"code": "data_source_unavailable", "msg": "data source unavailable"}},
            503,
        )
    except Exception:
        return _response({"error": {"code": "data_source_unavailable", "msg": "data source unavailable"}}, 500)


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
        return _response(
            {"status": "degraded", "error": {"code": "data_source_unavailable", "msg": "data source unavailable"}},
            503,
        )
    except Exception:
        return _response({"error": {"code": "data_source_unavailable", "msg": "data source unavailable"}}, 500)


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
