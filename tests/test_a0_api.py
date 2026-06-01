from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"

sys.path.insert(0, str(A0_DIR))

spec = util.spec_from_file_location("a0_api_app", A0_DIR / "app.py")
assert spec is not None
a0_api_app = util.module_from_spec(spec)
sys.modules["a0_api_app"] = a0_api_app
assert spec.loader is not None
spec.loader.exec_module(a0_api_app)

import serializers  # noqa: E402,I001


@pytest.fixture(autouse=True)
def _patch_clickhouse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        a0_api_app,
        "_query_clickhouse",
        lambda sql: [
            {
                "event_id": "evt-0001",
                "timestamp": "2026-05-29T08:12:03Z",
                "actor_agent_role": "coder",
                "actor_model_id": "qwen-max-2026",
                "actor_vendor_family": "alibaba",
                "actor_session_id": "session-1",
                "action_tool": "model-router",
                "action_skill": None,
                "action_operation": "route",
                "context_change_id": "change-1",
                "context_step": 6,
                "context_data_levels": ["L3"],
                "result_status": "success",
                "result_reason": "脱敏后路由 qwen-max",
                "result_duration_ms": 12.5,
                "input_hash": "a" * 64,
                "output_hash": "b" * 64,
                "prev_hash": "c" * 64,
                "current_hash": "routing#a1b2",
                "row_id": 1,
            },
            {
                "event_id": "evt-0002",
                "timestamp": "2026-05-29T08:15:41Z",
                "actor_agent_role": "coder",
                "actor_model_id": "dify-rag",
                "actor_vendor_family": "openai",
                "actor_session_id": "session-2",
                "action_tool": "prompt-injection-scan",
                "action_skill": None,
                "action_operation": "detect",
                "context_change_id": "change-1",
                "context_step": 0,
                "context_data_levels": ["L3"],
                "result_status": "blocked",
                "result_reason": "检索内容含可疑指令→隔离",
                "result_duration_ms": 2.1,
                "input_hash": "d" * 64,
                "output_hash": "e" * 64,
                "prev_hash": "f" * 64,
                "current_hash": "inj#c3d4",
                "row_id": 2,
            },
        ],
    )


def test_endpoints_return_contract_shapes() -> None:
    client = a0_api_app.make_test_client(a0_api_app.app)

    posture = client.get("/api/v1/posture")
    traffic = client.get("/api/v1/traffic")
    events = client.get("/api/v1/events")

    assert posture.status_code == 200
    assert traffic.status_code == 200
    assert events.status_code == 200

    posture_payload = posture.json()
    traffic_payload = traffic.json()
    events_payload = events.json()

    assert set(posture_payload) == {
        "composite",
        "compliance_score",
        "security_score",
        "gates",
        "alerts",
    }
    assert set(traffic_payload) == {"inbound", "outbound"}
    assert set(events_payload) == {"events"}
    assert len(posture_payload["gates"]) >= 6
    assert len(events_payload["events"]) >= 2


def test_white_listed_output_and_payload_null() -> None:
    client = a0_api_app.make_test_client(a0_api_app.app)
    payload = client.get("/api/v1/events").json()
    payload_json = json.dumps(payload, ensure_ascii=False)

    assert "prompt" not in payload_json
    assert "raw_text" not in payload_json
    assert "payload" in payload_json
    for event in payload["events"]:
        if event["cat"] == "sec":
            assert event["payload"] is None


def test_zero_phi_guard_rejects_phi_shape() -> None:
    with pytest.raises(serializers.PhiLeakError):
        serializers.assert_no_phi(
            {
                "events": [
                    {
                        "ts": "2026-05-29T08:22:55Z",
                        "cat": "sec",
                        "status": "yellow",
                        "upstream": "dev-local-batch",
                        "ctx": "dev",
                        "sec_type": "滥用",
                        "action": "高频调用→限流（规划 🚧）",
                        "ref": "rate#0f7a",
                        "payload": "原始入参不允许回显",
                    }
                ]
            },
            "GET /events",
        )


def test_clickhouse_unavailable_returns_generic_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_sql: str) -> list[dict[str, object]]:
        raise a0_api_app.ClickHouseUnavailable("HTTP request failed: /internal/path")

    monkeypatch.setattr(a0_api_app, "_query_clickhouse", unavailable)
    client = a0_api_app.make_test_client(a0_api_app.app)

    response = client.get("/api/v1/posture")
    payload = response.json()

    assert response.status_code == 503
    assert payload == {
        "status": "degraded",
        "error": {"code": "data_source_unavailable", "msg": "data source unavailable"},
    }
    assert "/internal/path" not in json.dumps(payload, ensure_ascii=False)
