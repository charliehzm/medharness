from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "model-router"))

from allowlist import Allowlist, AllowlistEntry  # noqa: E402
from heterogeneity import HeterogeneityPolicy  # noqa: E402
from policy import PolicyCore, RouteRequest  # noqa: E402


def _entry() -> AllowlistEntry:
    return AllowlistEntry(
        id="gpt-5",
        vendor_family="openai",
        deployment="private://gpt-5",
        allowed_agent_roles=("coder", "compliance", "reviewer", "docs", "maintainer"),
        allowed_data_levels=("L1", "L2", "L3"),
        rate_limit_qps=10,
    )


def _request(**overrides: object) -> RouteRequest:
    payload = {
        "model_id": "gpt-5",
        "agent_role": "coder",
        "data_level": "L2",
        "change_id": "change-001",
        "metadata": {"desensitized": True, "caller_vendor_family": "openai"},
    }
    payload.update(overrides)
    meta = dict(payload["metadata"])  # type: ignore[arg-type]
    meta.setdefault("tier_trusted", True)  # B1: tier attested unless a test drives the tier layer
    payload["metadata"] = meta
    return RouteRequest(**payload)  # type: ignore[arg-type]


def test_compliance_same_family_denies() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai", "claude-sonnet-4.6": "anthropic"})
    assert not policy.check(
        _request(
            agent_role="compliance",
            metadata={"desensitized": True, "caller_vendor_family": "openai"},
        ),
        _entry(),
    )


def test_compliance_cross_family_allows() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai", "claude-sonnet-4.6": "anthropic"})
    assert policy.check(
        _request(
            agent_role="compliance",
            metadata={"desensitized": True, "caller_vendor_family": "anthropic"},
        ),
        _entry(),
    )


def test_reviewer_same_family_denies() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    assert not policy.check(
        _request(
            agent_role="reviewer", metadata={"desensitized": True, "caller_vendor_family": "openai"}
        ),
        _entry(),
    )


def test_docs_low_risk_allows_same_family() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    assert policy.check(
        _request(
            agent_role="docs", metadata={"desensitized": True, "caller_vendor_family": "openai"}
        ),
        _entry(),
    )


def test_maintainer_override_allows_same_family() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    assert policy.check(
        _request(
            agent_role="maintainer",
            metadata={"desensitized": True, "caller_vendor_family": "openai"},
        ),
        _entry(),
    )


def test_missing_caller_vendor_family_denies_fail_closed() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    assert not policy.check(
        _request(agent_role="compliance", metadata={"desensitized": True}),
        _entry(),
    )


def test_docs_missing_caller_vendor_family_denies_fail_closed() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    assert not policy.check(
        _request(agent_role="docs", metadata={"desensitized": True}),
        _entry(),
    )


def test_unknown_agent_role_denies_fail_closed() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    assert not policy.check(
        _request(
            agent_role="science",
            metadata={"desensitized": True, "caller_vendor_family": "anthropic"},
        ),
        _entry(),
    )


def test_policy_core_with_heterogeneity_hook_denies_same_family() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai"})
    core = PolicyCore(_allowlist(), heterogeneity_check=policy.check)
    decision = core.evaluate(
        _request(
            agent_role="compliance",
            metadata={"desensitized": True, "caller_vendor_family": "openai"},
        )
    )

    assert decision.decision == "deny"
    assert decision.layer_failed == "heterogeneity"
    assert "heterogeneity policy denied" in decision.reason


def test_heterogeneity_check_is_fast_enough() -> None:
    policy = HeterogeneityPolicy({"gpt-5": "openai", "claude-sonnet-4.6": "anthropic"})
    request = _request(
        agent_role="compliance",
        metadata={"desensitized": True, "caller_vendor_family": "anthropic"},
    )
    entry = _entry()
    start = time.perf_counter_ns()
    for _ in range(100_000):
        assert policy.check(request, entry)
    elapsed_us = (time.perf_counter_ns() - start) // 1_000

    assert elapsed_us / 100_000 < 100


def _allowlist() -> Allowlist:
    return Allowlist(
        schema_version="T3.allowlist.v1",
        policy_version="change-001",
        entries=(_entry(),),
    )
