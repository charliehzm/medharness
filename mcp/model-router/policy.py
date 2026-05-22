"""Pure policy core for model-router runtime gating.

>>> from allowlist import Allowlist, AllowlistEntry
>>> allowlist = Allowlist(
...     schema_version="T3.allowlist.v1",
...     policy_version="change-001",
...     entries=(
...         AllowlistEntry(
...             id="qwen-max",
...             vendor_family="alibaba",
...             deployment="private://qwen-max",
...             allowed_agent_roles=("coder", "compliance"),
...             allowed_data_levels=("L1", "L2", "L3"),
...             rate_limit_qps=10,
...         ),
...     ),
... )
>>> core = PolicyCore(allowlist)
>>> decision = core.evaluate(RouteRequest(
...     model_id="qwen-max",
...     agent_role="coder",
...     data_level="L2",
...     change_id="change-001",
...     metadata={"desensitized": True},
... ))
>>> decision.decision
'allow'
>>> decision.policy_version
'change-001'
>>> denied = core.evaluate(RouteRequest(
...     model_id="qwen-max",
...     agent_role="coder",
...     data_level="L2",
...     change_id="change-001",
...     metadata={},
... ))
>>> denied.decision, denied.layer_failed
('deny', 'marker')
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from allowlist import Allowlist, AllowlistEntry

Decision = Literal["allow", "deny"]
Layer = Literal["allowlist", "heterogeneity", "data_level", "marker"]


@dataclass(frozen=True)
class RouteRequest:
    model_id: str
    agent_role: str
    data_level: str
    change_id: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class RouteDecision:
    decision: Decision
    reason: str
    layer_failed: Layer | None
    policy_version: str
    duration_us: int


class PolicyCore:
    def __init__(
        self,
        allowlist: Allowlist,
        *,
        heterogeneity_check: Callable[[RouteRequest, AllowlistEntry], bool] | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._heterogeneity_check = heterogeneity_check

    def evaluate(self, request: RouteRequest) -> RouteDecision:
        start = time.perf_counter_ns()
        if not self._has_desensitized_marker(request):
            return self._deny(
                request,
                f"request for model_id='{request.model_id}' agent_role='{request.agent_role}' data_level='{request.data_level}' must route through mcp-desensitize first",
                "marker",
                start,
            )

        entry = self._allowlist.lookup(request.model_id)
        if entry is None:
            return self._deny(
                request,
                f"model_id='{request.model_id}' not present in active allowlist agent_role='{request.agent_role}' data_level='{request.data_level}'",
                "allowlist",
                start,
            )

        if request.agent_role not in entry.allowed_agent_roles:
            return self._deny(
                request,
                f"agent_role='{request.agent_role}' not allowed for model_id='{request.model_id}' data_level='{request.data_level}'",
                "allowlist",
                start,
            )

        if request.data_level not in entry.allowed_data_levels:
            return self._deny(
                request,
                f"data_level='{request.data_level}' exceeds policy for model_id='{request.model_id}' agent_role='{request.agent_role}'",
                "data_level",
                start,
            )

        if self._heterogeneity_check is not None and not self._heterogeneity_check(request, entry):
            return self._deny(
                request,
                f"heterogeneity policy denied model_id='{request.model_id}' agent_role='{request.agent_role}' vendor_family='{entry.vendor_family}'",
                "heterogeneity",
                start,
            )

        return RouteDecision(
            decision="allow",
            reason=(
                f"allow model_id='{request.model_id}' agent_role='{request.agent_role}' "
                f"data_level='{request.data_level}' vendor_family='{entry.vendor_family}'"
            ),
            layer_failed=None,
            policy_version=self._allowlist.active_policy_version(),
            duration_us=self._duration_us(start),
        )

    def _deny(
        self,
        request: RouteRequest,
        reason: str,
        layer_failed: Layer,
        start_ns: int,
    ) -> RouteDecision:
        return RouteDecision(
            decision="deny",
            reason=reason,
            layer_failed=layer_failed,
            policy_version=self._allowlist.active_policy_version(),
            duration_us=self._duration_us(start_ns),
        )

    def _has_desensitized_marker(self, request: RouteRequest) -> bool:
        marker = request.metadata.get("desensitized")
        return marker is True

    @staticmethod
    def _duration_us(start_ns: int) -> int:
        return max(0, (time.perf_counter_ns() - start_ns) // 1_000)
