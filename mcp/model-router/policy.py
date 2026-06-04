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
...     metadata={"tier_trusted": True, "desensitized": True},
... ))
>>> decision.decision
'allow'
>>> decision.allowed_model_set
('qwen-max',)
>>> decision.policy_version
'change-001'
>>> denied = core.evaluate(RouteRequest(
...     model_id="qwen-max",
...     agent_role="coder",
...     data_level="L2",
...     change_id="change-001",
...     metadata={"tier_trusted": True},
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

Decision = Literal["allow", "deny", "reroute"]
Layer = Literal["tier", "allowlist", "heterogeneity", "data_level", "marker"]
Lane = Literal["normal", "sensitive"]

DATA_LEVEL_ORDER: tuple[str, ...] = ("L1", "L2", "L3", "L4")
DATA_LEVEL_RANK = {level: rank for rank, level in enumerate(DATA_LEVEL_ORDER)}


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
    allowed_model_set: tuple[str, ...] = ()
    lane: Lane | None = None
    max_data_level: str | None = None
    map_id: str | None = None


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
        if not request.metadata.get("tier_trusted", False):
            return self._deny(
                request,
                "tier fields not attested by gate middleware (caller-asserted tier rejected)",
                "tier",
                start,
            )
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
            reroute = self._reroute_if_possible(request, entry, start)
            if reroute is not None:
                return reroute
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

        candidates = self._candidate_entries(request, request.data_level)
        return RouteDecision(
            decision="allow",
            reason=(
                f"allow model_id='{request.model_id}' agent_role='{request.agent_role}' "
                f"data_level='{request.data_level}' vendor_family='{entry.vendor_family}'"
            ),
            layer_failed=None,
            policy_version=self._allowlist.active_policy_version(),
            duration_us=self._duration_us(start),
            allowed_model_set=self._model_ids(candidates),
            lane=self._lane_for(request.data_level),
            max_data_level=self._set_max_data_level(candidates),
            map_id=self._map_id(request),
        )

    def _reroute_if_possible(
        self,
        request: RouteRequest,
        entry: AllowlistEntry,
        start_ns: int,
    ) -> RouteDecision | None:
        if not self._is_level_exceeds(request.data_level, entry):
            return None

        map_id = self._map_id(request)
        if not self._has_desensitized_marker(request) or map_id is None:
            return None

        candidates = self._candidate_entries(request, request.data_level)
        if not candidates:
            return None

        return RouteDecision(
            decision="reroute",
            reason=(
                f"data_level='{request.data_level}' exceeds requested model_id='{request.model_id}' "
                "policy; reroute to sensitive lane allowed_model_set"
            ),
            layer_failed="data_level",
            policy_version=self._allowlist.active_policy_version(),
            duration_us=self._duration_us(start_ns),
            allowed_model_set=self._model_ids(candidates),
            lane="sensitive",
            max_data_level=self._set_max_data_level(candidates),
            map_id=map_id,
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

    def _candidate_entries(
        self,
        request: RouteRequest,
        data_level: str,
    ) -> tuple[AllowlistEntry, ...]:
        candidates: list[AllowlistEntry] = []
        for entry in self._allowlist.entries:
            if request.agent_role not in entry.allowed_agent_roles:
                continue
            if data_level not in entry.allowed_data_levels:
                continue
            if self._heterogeneity_check is not None and not self._heterogeneity_check(
                request, entry
            ):
                continue
            candidates.append(entry)
        return tuple(candidates)

    @staticmethod
    def _model_ids(entries: tuple[AllowlistEntry, ...]) -> tuple[str, ...]:
        return tuple(entry.id for entry in entries)

    @staticmethod
    def _lane_for(data_level: str) -> Lane:
        rank = DATA_LEVEL_RANK.get(data_level)
        if rank is None:
            return "sensitive"
        return "sensitive" if rank >= DATA_LEVEL_RANK["L3"] else "normal"

    @staticmethod
    def _set_max_data_level(entries: tuple[AllowlistEntry, ...]) -> str | None:
        max_levels = [
            max(
                (DATA_LEVEL_RANK[level] for level in entry.allowed_data_levels),
                default=-1,
            )
            for entry in entries
        ]
        if not max_levels:
            return None
        set_rank = max(max_levels)
        if set_rank < 0:
            return None
        return DATA_LEVEL_ORDER[set_rank]

    @staticmethod
    def _is_level_exceeds(data_level: str, entry: AllowlistEntry) -> bool:
        requested_rank = DATA_LEVEL_RANK.get(data_level)
        if requested_rank is None:
            return False
        entry_max = max(
            (DATA_LEVEL_RANK[level] for level in entry.allowed_data_levels),
            default=-1,
        )
        return requested_rank > entry_max

    @staticmethod
    def _map_id(request: RouteRequest) -> str | None:
        value = request.metadata.get("map_id")
        if value in (None, ""):
            return None
        return str(value)

    @staticmethod
    def _duration_us(start_ns: int) -> int:
        return max(0, (time.perf_counter_ns() - start_ns) // 1_000)
