from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROUTER_DIR = ROOT / "mcp" / "model-router"
SERVER = MODEL_ROUTER_DIR / "server_v2.py"

sys.path.insert(0, str(MODEL_ROUTER_DIR))

spec = util.spec_from_file_location("model_router_server_v2", SERVER)
assert spec is not None
server_v2 = util.module_from_spec(spec)
sys.modules["model_router_server_v2"] = server_v2
assert spec.loader is not None
spec.loader.exec_module(server_v2)


CHANGE_ID = "change-t3-server"


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    server_v2._RUNTIME = None


def _allowlist_path(tmp_path: Path) -> Path:
    path = tmp_path / "openspec" / "changes" / CHANGE_ID / "MODEL_ALLOWLIST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "T3.allowlist.v1",
                "policy_version": "policy-t3.6",
                "models": [
                    {
                        "id": "qwen-max",
                        "vendor_family": "alibaba",
                        "deployment": "private://qwen-max",
                        "allowed_agent_roles": ["coder", "compliance", "docs", "maintainer"],
                        "allowed_data_levels": ["L1", "L2", "L3"],
                        "rate_limit_qps": 2,
                    },
                    {
                        "id": "claude-sonnet-4.6",
                        "vendor_family": "anthropic",
                        "deployment": "private://claude-sonnet-4.6",
                        "allowed_agent_roles": ["coder", "compliance", "reviewer", "docs"],
                        "allowed_data_levels": ["L1", "L2"],
                        "rate_limit_qps": 10,
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _route_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model_id": "qwen-max",
        "agent_role": "coder",
        "data_level": "L2",
        "change_id": CHANGE_ID,
        "caller_vendor_family": "openai",
        "desensitized": True,
    }
    payload.update(overrides)
    return payload


def _audit_lines(tmp_path: Path) -> list[dict[str, object]]:
    audit_path = tmp_path / ".audit" / "routing_log.jsonl"
    assert audit_path.exists()
    return [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line
    ]


def test_route_health_and_stdio_smoke(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)

    allow = server_v2.route_v2(_route_payload())
    health = server_v2.health_v2()

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    route_cli = subprocess.run(
        [sys.executable, str(SERVER), "route"],
        input=json.dumps(_route_payload(prompt="RAW-PHI-CLAIM"), ensure_ascii=False),
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=10,
    )
    route_stdio = subprocess.run(
        [sys.executable, str(SERVER), "serve", "--stdio"],
        input=json.dumps(
            {"id": "route-1", "method": "route", "params": _route_payload(prompt="RAW-PHI-CLAIM")},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps({"id": "health-1", "method": "health", "params": {}}, ensure_ascii=False)
        + "\n",
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=10,
    )

    cli_payload = json.loads(route_cli.stdout)
    stdio_payloads = [json.loads(line) for line in route_stdio.stdout.splitlines() if line]

    assert allow["decision"] == "allow"
    assert allow["model_id"] == "qwen-max"
    assert allow["vendor_family"] == "alibaba"
    assert allow["deployment"] == "private://qwen-max"
    assert allow["routing_log_id"]
    assert allow["policy_version"] == "policy-t3.6"
    assert allow["_meta"]["duration_ms"] >= 0

    assert health["status"] == "ok-v2"
    assert health["policy_version"] == "policy-t3.6"
    assert health["circuit_open_count"] == 0

    assert cli_payload["decision"] == "allow"
    assert cli_payload["routing_log_id"]
    assert route_stdio.returncode == 0
    assert stdio_payloads[0]["result"]["decision"] == "allow"
    assert stdio_payloads[1]["result"]["status"] == "ok-v2"

    audit_text = (tmp_path / ".audit" / "routing_log.jsonl").read_text(encoding="utf-8")
    assert "RAW-PHI-CLAIM" not in audit_text
    assert "prompt" not in audit_text


def test_missing_desensitized_marker_denies(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    denied = server_v2.route_v2(_route_payload(desensitized=False))

    assert denied["decision"] == "deny"
    assert denied["error"]["layer_failed"] == "marker"
    assert denied["error"]["type"] == "PolicyDenyError"
    assert "must route through mcp-desensitize first" in denied["error"]["message"]


def test_allowlist_miss_denies(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    denied = server_v2.route_v2(_route_payload(model_id="missing-model"))

    assert denied["decision"] == "deny"
    assert denied["error"]["layer_failed"] == "allowlist"
    assert "missing-model" in denied["error"]["message"]


def test_data_level_over_policy_denies(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    denied = server_v2.route_v2(_route_payload(data_level="L4"))

    assert denied["decision"] == "deny"
    assert denied["error"]["layer_failed"] == "data_level"
    assert denied["error"]["type"] == "PolicyDenyError"
    assert "data_level='L4'" in denied["error"]["message"]


def test_same_family_compliance_call_denies(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    denied = server_v2.route_v2(
        _route_payload(
            agent_role="compliance",
            caller_vendor_family="alibaba",
        )
    )

    assert denied["decision"] == "deny"
    assert denied["error"]["layer_failed"] == "heterogeneity"
    assert denied["error"]["severity"] == "WARN"
    assert "heterogeneity policy denied" in denied["error"]["message"]


def test_five_denies_open_circuit_and_sixth_is_sev2(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    for _ in range(5):
        denied = server_v2.route_v2(
            _route_payload(
                model_id="claude-sonnet-4.6",
                data_level="L2",
                agent_role="compliance",
                caller_vendor_family="anthropic",
            )
        )
        assert denied["decision"] == "deny"
        assert denied["error"]["layer_failed"] == "heterogeneity"

    opened = server_v2.route_v2(
        _route_payload(
            model_id="claude-sonnet-4.6",
            data_level="L2",
            agent_role="compliance",
            caller_vendor_family="anthropic",
        )
    )

    assert opened["decision"] == "deny"
    assert opened["error"]["layer_failed"] == "circuit"
    assert opened["error"]["type"] == "CircuitOpenError"
    assert opened["error"]["severity"] == "SEV-2"

    health = server_v2.health_v2()
    assert health["circuit_open_count"] >= 1


def test_rate_limit_denies_when_burst_exceeds_qps(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    first = server_v2.route_v2(_route_payload())
    second = server_v2.route_v2(_route_payload())
    third = server_v2.route_v2(_route_payload())

    assert first["decision"] == "allow"
    assert second["decision"] == "allow"
    assert third["decision"] == "deny"
    assert third["error"]["layer_failed"] == "rate"
    assert third["error"]["type"] == "RateLimitError"


def test_routing_log_ids_are_unique_and_audit_records_are_structured(tmp_path: Path) -> None:
    _allowlist_path(tmp_path)
    first = server_v2.route_v2(_route_payload())
    second = server_v2.route_v2(
        _route_payload(model_id="claude-sonnet-4.6", caller_vendor_family="openai")
    )

    assert first["routing_log_id"] != second["routing_log_id"]

    records = _audit_lines(tmp_path)
    assert len(records) >= 2
    for record in records:
        assert "decision" in record
        assert "reason" in record
        assert "duration_ms" in record
        assert "prompt" not in record
        assert "RAW-PHI-CLAIM" not in json.dumps(record, ensure_ascii=False)
