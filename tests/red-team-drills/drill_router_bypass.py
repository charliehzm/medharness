#!/usr/bin/env python3
"""Red-team drill 2: router bypass detection on synthetic allowlists.

All cases are local-only, synthetic, and fail closed when the router allows an
expected-deny vector.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "mcp" / "model-router" / "server_v2.py"
SCHEMA_VERSION = "T3.router_bypass.v1"
DEFAULT_CASES = [
    {
        "case_id": "direct-openai-endpoint",
        "vector": "model_id=gpt-4o",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-4o",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-bypass",
            "caller_vendor_family": "openai",
            "desensitized": True,
        },
    },
    {
        "case_id": "direct-anthropic-endpoint",
        "vector": "model_id=claude-opus-4.7",
        "expected_decision": "deny",
        "payload": {
            "model_id": "claude-opus-4.7",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-bypass",
            "caller_vendor_family": "openai",
            "desensitized": True,
        },
    },
    {
        "case_id": "openrouter-bypass",
        "vector": "model_id=openrouter/auto",
        "expected_decision": "deny",
        "payload": {
            "model_id": "openrouter/auto",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-bypass",
            "caller_vendor_family": "openai",
            "desensitized": True,
        },
    },
    {
        "case_id": "same-family-reviewer",
        "vector": "agent_role=reviewer caller_vendor_family=anthropic",
        "expected_decision": "deny",
        "payload": {
            "model_id": "claude-sonnet-4.6",
            "agent_role": "reviewer",
            "data_level": "L2",
            "change_id": "change-router-hetero",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
    },
    {
        "case_id": "same-family-compliance",
        "vector": "agent_role=compliance caller_vendor_family=anthropic",
        "expected_decision": "deny",
        "payload": {
            "model_id": "claude-sonnet-4.6",
            "agent_role": "compliance",
            "data_level": "L2",
            "change_id": "change-router-hetero",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
    },
    {
        "case_id": "l4-over-policy",
        "vector": "data_level=L4",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-5",
            "agent_role": "coder",
            "data_level": "L4",
            "change_id": "change-router-bypass",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
    },
    {
        "case_id": "missing-marker",
        "vector": "desensitized=false",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-5",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-bypass",
            "caller_vendor_family": "anthropic",
            "desensitized": False,
        },
    },
    {
        "case_id": "missing-allowlist-file",
        "vector": "change_id=change-router-missing",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-5",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-missing",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
    },
    {
        "case_id": "malformed-allowlist",
        "vector": "broken MODEL_ALLOWLIST.json",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-5",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-malformed",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
    },
    {
        "case_id": "expired-allowlist",
        "vector": "policy_version missing",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-5",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-expired",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
    },
    {
        "case_id": "rate-limit-burst",
        "vector": "burst qps+1",
        "expected_decision": "deny",
        "payload": {
            "model_id": "gpt-5",
            "agent_role": "coder",
            "data_level": "L2",
            "change_id": "change-router-burst",
            "caller_vendor_family": "anthropic",
            "desensitized": True,
        },
        "burst": 3,
    },
]


def _write_allowlist(root: Path, change_id: str, payload: dict[str, Any]) -> Path:
    target = root / "openspec" / "changes" / change_id / "MODEL_ALLOWLIST.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _write_raw(root: Path, change_id: str, raw_text: str) -> Path:
    target = root / "openspec" / "changes" / change_id / "MODEL_ALLOWLIST.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw_text, encoding="utf-8")
    return target


def _render_allowlist_models(
    model_id: str, vendor_family: str, allowed_roles: list[str], allowed_levels: list[str], qps: int
) -> dict[str, Any]:
    return {
        "id": model_id,
        "vendor_family": vendor_family,
        "deployment": f"private://{model_id}",
        "allowed_agent_roles": allowed_roles,
        "allowed_data_levels": allowed_levels,
        "rate_limit_qps": qps,
    }


def _seed_allowlists(root: Path) -> None:
    _write_allowlist(
        root,
        "change-router-bypass",
        {
            "schema_version": "T3.allowlist.v1",
            "policy_version": "policy-router-bypass",
            "models": [
                _render_allowlist_models(
                    "gpt-5",
                    "openai",
                    ["coder", "docs"],
                    ["L1", "L2"],
                    2,
                )
            ],
        },
    )
    _write_allowlist(
        root,
        "change-router-malformed",
        {
            "schema_version": "T3.allowlist.v1",
            "policy_version": "policy-router-malformed",
            "models": [],
        },
    )
    _write_raw(root, "change-router-malformed", "{")
    _write_allowlist(
        root,
        "change-router-hetero",
        {
            "schema_version": "T3.allowlist.v1",
            "policy_version": "policy-router-hetero",
            "models": [
                _render_allowlist_models(
                    "claude-sonnet-4.6",
                    "anthropic",
                    ["reviewer", "compliance"],
                    ["L1", "L2"],
                    4,
                )
            ],
        },
    )
    _write_allowlist(
        root,
        "change-router-expired",
        {
            "schema_version": "T3.allowlist.v1",
            "policy_version": "",
            "models": [_render_allowlist_models("gpt-5", "openai", ["coder"], ["L1", "L2"], 2)],
        },
    )
    _write_allowlist(
        root,
        "change-router-burst",
        {
            "schema_version": "T3.allowlist.v1",
            "policy_version": "policy-router-burst",
            "models": [
                _render_allowlist_models("gpt-5", "openai", ["coder", "docs"], ["L1", "L2"], 2)
            ],
        },
    )


def _route(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(root)
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


def _route_stdio(root: Path, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(root)
    body = "\n".join(
        json.dumps({"id": f"case-{i}", "method": "route", "params": payload}, ensure_ascii=False)
        for i, payload in enumerate(payloads, start=1)
    )
    proc = subprocess.run(
        [sys.executable, str(SERVER), "serve", "--stdio"],
        input=body + "\n",
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=10,
    )
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def _run_case(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    payload = dict(case["payload"])
    if case["case_id"] == "rate-limit-burst":
        responses = _route_stdio(root, [payload, payload, payload])
        actual = responses[-1]["result"]
        actual_decision = "deny" if "error" in actual else str(actual.get("decision", "allow"))
        reason = actual.get("error", {}).get("message", "") if isinstance(actual, dict) else ""
        return {
            "case_id": case["case_id"],
            "vector": case["vector"],
            "expected_decision": case["expected_decision"],
            "actual_decision": actual_decision,
            "reason": reason,
        }

    response = _route(root, payload)
    actual_decision = str(response.get("decision", "deny"))
    reason = response.get("error", {}).get("message", "") if isinstance(response, dict) else ""
    return {
        "case_id": case["case_id"],
        "vector": case["vector"],
        "expected_decision": case["expected_decision"],
        "actual_decision": actual_decision,
        "reason": reason,
    }


def _build_report(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    failed_case_ids = [
        result["case_id"]
        for result in results
        if result["expected_decision"] == "deny" and result["actual_decision"] == "allow"
    ]
    passed = not failed_case_ids
    return {
        "schema_version": SCHEMA_VERSION,
        "drill": "router_bypass",
        "total_cases": len(cases),
        "passed": passed,
        "failed_case_ids": failed_case_ids,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_allowlists(root)
        cases = DEFAULT_CASES
        results = [_run_case(root, case) for case in cases]
        report = _build_report(cases, results)
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
