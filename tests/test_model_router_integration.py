from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp" / "model-router" / "server_v2.py"
FIXTURE = ROOT / "tests" / "fixtures" / "model_router_allowlists.json"


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write_allowlist(tmp_path: Path, change_id: str, payload: dict[str, object]) -> Path:
    target = tmp_path / "openspec" / "changes" / change_id / "MODEL_ALLOWLIST.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    allowlist = {
        "schema_version": "T3.allowlist.v1",
        "policy_version": payload["policy_version"],
        "models": payload["models"],
    }
    target.write_text(json.dumps(allowlist, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _route_request(
    *,
    model_id: str,
    agent_role: str,
    data_level: str,
    change_id: str,
    caller_vendor_family: str,
    desensitized: bool,
) -> dict[str, object]:
    return {
        "model_id": model_id,
        "agent_role": agent_role,
        "data_level": data_level,
        "change_id": change_id,
        "caller_vendor_family": caller_vendor_family,
        "desensitized": desensitized,
    }


def _run_route(tmp_path: Path, payload: dict[str, object]) -> dict[str, object]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SERVER), "route"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=10,
    )
    return json.loads(proc.stdout)


def _run_stdio(tmp_path: Path, payloads: list[dict[str, object]]) -> list[dict[str, object]]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    request_text = "\n".join(
        json.dumps({"id": f"req-{index}", "method": "route", "params": payload}, ensure_ascii=False)
        for index, payload in enumerate(payloads, start=1)
    )
    proc = subprocess.run(
        [sys.executable, str(SERVER), "serve", "--stdio"],
        input=request_text + "\n",
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=10,
    )
    return [json.loads(line) for line in proc.stdout.splitlines() if line]


def _audit_text(tmp_path: Path) -> str:
    audit_path = tmp_path / ".audit" / "routing_log.jsonl"
    assert audit_path.exists()
    return audit_path.read_text(encoding="utf-8")


@pytest.fixture()
def fixture_data() -> dict[str, object]:
    return _load_fixture()


def test_model_router_e2e_scenarios(tmp_path: Path, monkeypatch, fixture_data: dict[str, object]) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    for change in fixture_data["changes"]:  # type: ignore[index]
        change_id = change["change_id"]  # type: ignore[index]
        _write_allowlist(tmp_path, change_id, change)  # type: ignore[arg-type]

    raw_payload_sentinel = "SYNTHETIC-RAW-PAYLOAD-SHOULD-NOT-ENTER-AUDIT"
    happy_payload = _route_request(
        model_id="deepseek-v3",
        agent_role="coder",
        data_level="L2",
        change_id="change-router-happy",
        caller_vendor_family="openai",
        desensitized=True,
    )
    happy_payload["prompt"] = raw_payload_sentinel
    happy = _run_route(
        tmp_path,
        happy_payload,
    )
    public_direct = _run_route(
        tmp_path,
        _route_request(
            model_id="gpt-4o",
            agent_role="coder",
            data_level="L2",
            change_id="change-router-public-direct",
            caller_vendor_family="openai",
            desensitized=True,
        ),
    )
    hetero = _run_route(
        tmp_path,
        _route_request(
            model_id="claude-sonnet-4.6",
            agent_role="compliance",
            data_level="L2",
            change_id="change-router-hetero",
            caller_vendor_family="anthropic",
            desensitized=True,
        ),
    )
    marker = _run_route(
        tmp_path,
        _route_request(
            model_id="qwen-max",
            agent_role="coder",
            data_level="L4",
            change_id="change-router-marker",
            caller_vendor_family="openai",
            desensitized=False,
        ),
    )

    stdio = _run_stdio(
        tmp_path,
        [
            _route_request(
                model_id="deepseek-v3",
                agent_role="coder",
                data_level="L2",
                change_id="change-router-happy",
                caller_vendor_family="openai",
                desensitized=True,
            ),
            _route_request(
                model_id="gpt-4o",
                agent_role="coder",
                data_level="L2",
                change_id="change-router-public-direct",
                caller_vendor_family="openai",
                desensitized=True,
            ),
            _route_request(
                model_id="gpt-5",
                agent_role="coder",
                data_level="L2",
                change_id="change-router-burst",
                caller_vendor_family="openai",
                desensitized=True,
            ),
            _route_request(
                model_id="gpt-5",
                agent_role="coder",
                data_level="L2",
                change_id="change-router-burst",
                caller_vendor_family="openai",
                desensitized=True,
            ),
            _route_request(
                model_id="gpt-5",
                agent_role="coder",
                data_level="L2",
                change_id="change-router-burst",
                caller_vendor_family="openai",
                desensitized=True,
            ),
        ],
    )

    assert happy["decision"] == "allow"
    assert happy["vendor_family"] == "deepseek"
    assert public_direct["decision"] == "deny"
    assert public_direct["error"]["layer_failed"] == "allowlist"
    assert hetero["decision"] == "deny"
    assert hetero["error"]["layer_failed"] == "heterogeneity"
    assert marker["decision"] == "deny"
    assert marker["error"]["layer_failed"] == "marker"
    assert stdio[0]["result"]["decision"] == "allow"
    assert stdio[1]["result"]["decision"] == "deny"
    assert stdio[1]["result"]["error"]["layer_failed"] == "allowlist"
    assert stdio[2]["result"]["decision"] == "allow"
    assert stdio[3]["result"]["decision"] == "allow"
    assert stdio[4]["result"]["decision"] == "deny"
    assert stdio[4]["result"]["error"]["layer_failed"] == "rate"

    audit_text = _audit_text(tmp_path)
    assert "prompt" not in audit_text
    assert "raw" not in audit_text
    assert raw_payload_sentinel not in audit_text
    assert json.dumps(happy_payload, ensure_ascii=False) not in audit_text
    assert "SYNTHETIC-RAW-PAYLOAD-SHOULD-NOT-ENTER-AUDIT" not in audit_text

    assert "deepseek-v3" in json.dumps(happy, ensure_ascii=False)
    assert "gpt-4o" in json.dumps(public_direct, ensure_ascii=False)
    assert "anthropic" in json.dumps(hetero, ensure_ascii=False)
