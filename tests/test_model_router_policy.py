from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "model-router"))

from allowlist import Allowlist, AllowlistEntry  # noqa: E402
from policy import PolicyCore, RouteRequest  # noqa: E402


def _allowlist() -> Allowlist:
    return Allowlist(
        schema_version="T3.allowlist.v1",
        policy_version="change-001",
        entries=(
            AllowlistEntry(
                id="qwen-max",
                vendor_family="alibaba",
                deployment="private://qwen-max",
                allowed_agent_roles=("coder", "compliance"),
                allowed_data_levels=("L1", "L2", "L3"),
                rate_limit_qps=10,
            ),
            AllowlistEntry(
                id="gpt-5",
                vendor_family="openai",
                deployment="private://gpt-5",
                allowed_agent_roles=("docs",),
                allowed_data_levels=("L1",),
                rate_limit_qps=5,
            ),
        ),
    )


def _request(**overrides: object) -> RouteRequest:
    payload = {
        "model_id": "qwen-max",
        "agent_role": "coder",
        "data_level": "L2",
        "change_id": "change-001",
        "metadata": {"desensitized": True},
    }
    payload.update(overrides)
    meta = dict(payload["metadata"])  # type: ignore[arg-type]
    meta.setdefault("tier_trusted", True)  # B1: tier attested unless a test drives the tier layer
    payload["metadata"] = meta
    return RouteRequest(**payload)  # type: ignore[arg-type]


def test_allow_happy_path() -> None:
    core = PolicyCore(_allowlist())
    decision = core.evaluate(_request())

    assert decision.decision == "allow"
    assert decision.layer_failed is None
    assert decision.policy_version == "change-001"
    assert "model_id='qwen-max'" in decision.reason
    assert "agent_role='coder'" in decision.reason
    assert "data_level='L2'" in decision.reason


def test_missing_desensitized_marker_denies() -> None:
    core = PolicyCore(_allowlist())
    decision = core.evaluate(_request(metadata={}))

    assert decision.decision == "deny"
    assert decision.layer_failed == "marker"
    assert "must route through mcp-desensitize first" in decision.reason
    assert "qwen-max" in decision.reason


def test_unknown_model_denies_at_allowlist_layer() -> None:
    core = PolicyCore(_allowlist())
    decision = core.evaluate(_request(model_id="unknown-model"))

    assert decision.decision == "deny"
    assert decision.layer_failed == "allowlist"
    assert "model_id='unknown-model'" in decision.reason
    assert "agent_role='coder'" in decision.reason
    assert "data_level='L2'" in decision.reason


def test_agent_role_veto_denies_at_allowlist_layer() -> None:
    core = PolicyCore(_allowlist())
    decision = core.evaluate(_request(agent_role="docs"))

    assert decision.decision == "deny"
    assert decision.layer_failed == "allowlist"
    assert "agent_role='docs'" in decision.reason
    assert "model_id='qwen-max'" in decision.reason
    assert "data_level='L2'" in decision.reason


def test_data_level_veto_denies_at_data_level_layer() -> None:
    core = PolicyCore(_allowlist())
    decision = core.evaluate(_request(data_level="L4"))

    assert decision.decision == "deny"
    assert decision.layer_failed == "data_level"
    assert "data_level='L4'" in decision.reason
    assert "model_id='qwen-max'" in decision.reason
    assert "agent_role='coder'" in decision.reason


def test_reason_is_auditable_and_contains_no_raw_phi() -> None:
    core = PolicyCore(_allowlist())
    decision = core.evaluate(_request())

    assert "张" not in decision.reason
    assert "110101199001011234" not in decision.reason
    assert "PHI" not in decision.reason


def test_heterogeneity_hook_can_deny_without_embedding_policy() -> None:
    core = PolicyCore(_allowlist(), heterogeneity_check=lambda _req, _entry: False)
    decision = core.evaluate(_request())

    assert decision.decision == "deny"
    assert decision.layer_failed == "heterogeneity"
    assert "heterogeneity policy denied" in decision.reason
    assert "vendor_family='alibaba'" in decision.reason


def test_policy_core_is_pure_and_fast_enough() -> None:
    core = PolicyCore(_allowlist())
    request = _request()
    start = time.perf_counter_ns()
    for _ in range(10_000):
        decision = core.evaluate(request)
        assert decision.decision == "allow"
    elapsed_us = (time.perf_counter_ns() - start) // 1_000

    assert elapsed_us / 10_000 < 1000
