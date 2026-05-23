"""Agent-role versus vendor-family heterogeneity policy.

>>> from allowlist import AllowlistEntry
>>> from policy import RouteRequest
>>> policy = HeterogeneityPolicy({"gpt-5": "openai", "claude-sonnet-4.6": "anthropic"})
>>> policy.check(RouteRequest(
...     model_id="gpt-5",
...     agent_role="compliance",
...     data_level="L2",
...     change_id="change-001",
...     metadata={"desensitized": True, "caller_vendor_family": "openai"},
... ), AllowlistEntry(
...     id="gpt-5",
...     vendor_family="openai",
...     deployment="private://gpt-5",
...     allowed_agent_roles=("coder", "compliance"),
...     allowed_data_levels=("L1", "L2"),
...     rate_limit_qps=10,
... ))
False
>>> policy.check(RouteRequest(
...     model_id="gpt-5",
...     agent_role="docs",
...     data_level="L2",
...     change_id="change-001",
...     metadata={"desensitized": True, "caller_vendor_family": "openai"},
... ), AllowlistEntry(
...     id="gpt-5",
...     vendor_family="openai",
...     deployment="private://gpt-5",
...     allowed_agent_roles=("coder", "compliance", "docs"),
...     allowed_data_levels=("L1", "L2"),
...     rate_limit_qps=10,
... ))
True
"""

from __future__ import annotations

from dataclasses import dataclass

from allowlist import AllowlistEntry
from policy import RouteRequest


@dataclass(frozen=True)
class HeterogeneityRule:
    caller_role: str
    same_family_allowed: bool


HETEROGENEITY_RULES = {
    "compliance": HeterogeneityRule("compliance", same_family_allowed=False),
    "reviewer": HeterogeneityRule("reviewer", same_family_allowed=False),
    "docs": HeterogeneityRule("docs", same_family_allowed=True),
    "maintainer": HeterogeneityRule("maintainer", same_family_allowed=True),
    "coder": HeterogeneityRule("coder", same_family_allowed=True),
}


class HeterogeneityPolicy:
    def __init__(self, vendor_family_map: dict[str, str]) -> None:
        self._vendor_family_map = dict(vendor_family_map)
        self._declared_vendor_families = set(vendor_family_map.values())

    def check(self, request: RouteRequest, entry: AllowlistEntry) -> bool:
        caller_role = request.agent_role
        caller_family = request.metadata.get("caller_vendor_family")

        if caller_role not in HETEROGENEITY_RULES:
            return False
        if not isinstance(caller_family, str) or not caller_family.strip():
            return False

        rule = HETEROGENEITY_RULES[caller_role]

        target_family = self._vendor_family_map.get(entry.id, entry.vendor_family)
        if target_family not in self._declared_vendor_families:
            return False

        if caller_role in {"docs", "maintainer", "coder"}:
            return True

        if not rule.same_family_allowed:
            return caller_family != target_family
        return True
