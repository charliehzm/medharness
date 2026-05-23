#!/usr/bin/env python3
"""mcp-model-router v2 · T3 runtime gate integration.

Wires together T3.1-T3.5:
- vendor_families.yml
- MODEL_ALLOWLIST.json hot loader
- PolicyCore
- HeterogeneityPolicy
- CircuitBreaker + RateLimiter
- AuditAdapter
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from allowlist import AllowlistError, HotAllowlist  # noqa: E402
from heterogeneity import HeterogeneityPolicy  # noqa: E402
from limits import CircuitBreaker, RateLimiter  # noqa: E402
from policy import PolicyCore, RouteDecision, RouteRequest  # noqa: E402
from vendor_families import DEFAULT_VENDOR_FAMILIES_PATH, load_vendor_families  # noqa: E402

LOGGER = logging.getLogger(__name__)
VENDOR_FAMILIES_PATH = DEFAULT_VENDOR_FAMILIES_PATH


def _project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()


def _allowlist_path(change_id: str) -> Path:
    return _project_root() / "openspec" / "changes" / change_id / "MODEL_ALLOWLIST.json"


def _audit_path() -> Path:
    return _project_root() / ".audit" / "routing_log.jsonl"


@dataclass
class _RuntimeState:
    vendor_family_map: dict[str, str]
    heterogeneity_policy: HeterogeneityPolicy
    allowlist_cache: dict[str, HotAllowlist] = field(default_factory=dict)
    rate_limiters: dict[str, tuple[int, RateLimiter]] = field(default_factory=dict)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    audit_adapter: AuditAdapter = field(default_factory=lambda: FileAuditAdapter())
    last_policy_version: str = ""

    def allowlist_for(self, change_id: str) -> HotAllowlist:
        hot = self.allowlist_cache.get(change_id)
        if hot is None:
            hot = HotAllowlist(
                _allowlist_path(change_id), vendor_families_path=VENDOR_FAMILIES_PATH
            )
            self.allowlist_cache[change_id] = hot
        return hot

    def rate_limiter_for(self, model_id: str, qps: int) -> RateLimiter:
        cached = self.rate_limiters.get(model_id)
        if cached is None or cached[0] != qps:
            cached = (qps, RateLimiter(qps))
            self.rate_limiters[model_id] = cached
        return cached[1]

    def circuit_open_count(self) -> int:
        count = 0
        for agent_role, change_id in list(self.circuit_breaker._rejects.keys()):
            if self.circuit_breaker.is_open(agent_role, change_id):
                count += 1
        return count


_RUNTIME: _RuntimeState | None = None


def _runtime() -> _RuntimeState:
    global _RUNTIME
    if _RUNTIME is None:
        vendor_family_map = load_vendor_families(VENDOR_FAMILIES_PATH)
        _RUNTIME = _RuntimeState(
            vendor_family_map=vendor_family_map,
            heterogeneity_policy=HeterogeneityPolicy(vendor_family_map),
        )
    return _RUNTIME


class AuditAdapter(ABC):
    @abstractmethod
    def write_routing_decision(self, record: dict[str, Any]) -> str:
        raise NotImplementedError


class FileAuditAdapter(AuditAdapter):
    def __init__(self, audit_path: Path | None = None) -> None:
        self._audit_path = audit_path or _audit_path()

    def write_routing_decision(self, record: dict[str, Any]) -> str:
        routing_log_id = record.get("routing_log_id") or uuid.uuid4().hex
        record["routing_log_id"] = routing_log_id
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return str(routing_log_id)


class ClickHouseAuditAdapter(AuditAdapter):
    """T4 placeholder. v0.5.0 edge tier writes file audit only."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError("ClickHouseAuditAdapter not implemented in v0.5.0 edge tier")

    def write_routing_decision(self, record: dict[str, Any]) -> str:
        del record
        raise NotImplementedError("ClickHouseAuditAdapter not implemented in v0.5.0 edge tier")


def _build_request(payload: dict[str, Any]) -> RouteRequest:
    required = ("model_id", "agent_role", "data_level", "change_id")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    metadata: dict[str, object] = {
        "desensitized": bool(payload.get("desensitized", False)),
    }
    if "caller_vendor_family" in payload and payload["caller_vendor_family"] is not None:
        metadata["caller_vendor_family"] = str(payload["caller_vendor_family"])

    return RouteRequest(
        model_id=str(payload["model_id"]),
        agent_role=str(payload["agent_role"]),
        data_level=str(payload["data_level"]),
        change_id=str(payload["change_id"]),
        metadata=metadata,
    )


def _base_response(
    *,
    decision: str,
    model_id: str,
    vendor_family: str,
    deployment: str,
    routing_log_id: str,
    policy_version: str,
    duration_ms: float,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "model_id": model_id,
        "vendor_family": vendor_family,
        "deployment": deployment,
        "routing_log_id": routing_log_id,
        "policy_version": policy_version,
        "_meta": {"duration_ms": round(duration_ms, 3)},
    }


def _error_response(
    *,
    decision: str,
    model_id: str,
    vendor_family: str,
    deployment: str,
    routing_log_id: str,
    policy_version: str,
    duration_ms: float,
    error_type: str,
    message: str,
    layer_failed: str,
    severity: str | None = None,
) -> dict[str, Any]:
    response = _base_response(
        decision=decision,
        model_id=model_id,
        vendor_family=vendor_family,
        deployment=deployment,
        routing_log_id=routing_log_id,
        policy_version=policy_version,
        duration_ms=duration_ms,
    )
    error = {"type": error_type, "message": message, "layer_failed": layer_failed}
    if severity is not None:
        error["severity"] = severity
    response["error"] = error
    return response


def _audit_record(
    *,
    routing_log_id: str,
    request: RouteRequest,
    decision: str,
    reason: str,
    policy_version: str,
    duration_ms: float,
    layer_failed: str | None,
    severity: str | None,
    model_id: str,
    vendor_family: str,
    deployment: str,
    error_type: str | None,
) -> dict[str, Any]:
    return {
        "routing_log_id": routing_log_id,
        "decision": decision,
        "reason": reason,
        "policy_version": policy_version,
        "duration_ms": round(duration_ms, 3),
        "layer_failed": layer_failed,
        "severity": severity,
        "error_type": error_type,
        "model_id": request.model_id,
        "agent_role": request.agent_role,
        "data_level": request.data_level,
        "change_id": request.change_id,
        "caller_vendor_family": request.metadata.get("caller_vendor_family", ""),
        "desensitized": request.metadata.get("desensitized", False),
        "target_model_id": model_id,
        "vendor_family": vendor_family,
        "deployment": deployment,
    }


def _invalid_request_response(
    payload: dict[str, Any],
    *,
    message: str,
    started: float,
) -> dict[str, Any]:
    runtime = _runtime()
    request = RouteRequest(
        model_id=str(payload.get("model_id", "")),
        agent_role=str(payload.get("agent_role", "")),
        data_level=str(payload.get("data_level", "")),
        change_id=str(payload.get("change_id", "")),
        metadata={"desensitized": bool(payload.get("desensitized", False))},
    )
    routing_log_id = uuid.uuid4().hex
    duration_ms = (time.perf_counter() - started) * 1000
    runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
    record = _audit_record(
        routing_log_id=routing_log_id,
        request=request,
        decision="deny",
        reason=message,
        policy_version=runtime.last_policy_version,
        duration_ms=duration_ms,
        layer_failed="request",
        severity="WARN",
        model_id=request.model_id,
        vendor_family="",
        deployment="",
        error_type="InvalidRequestError",
    )
    runtime.audit_adapter.write_routing_decision(record)
    return _error_response(
        decision="deny",
        model_id=request.model_id,
        vendor_family="",
        deployment="",
        routing_log_id=routing_log_id,
        policy_version=runtime.last_policy_version,
        duration_ms=duration_ms,
        error_type="InvalidRequestError",
        message=message,
        layer_failed="request",
        severity="WARN",
    )


def _open_circuit_response(request: RouteRequest, duration_ms: float) -> dict[str, Any]:
    runtime = _runtime()
    allowlist = None
    vendor_family = ""
    deployment = ""
    policy_version = runtime.last_policy_version
    try:
        allowlist = runtime.allowlist_for(request.change_id).get_allowlist()
        policy_version = allowlist.active_policy_version()
        entry = allowlist.lookup(request.model_id)
        if entry is not None:
            vendor_family = entry.vendor_family
            deployment = entry.deployment
    except Exception:
        pass

    routing_log_id = uuid.uuid4().hex
    record = _audit_record(
        routing_log_id=routing_log_id,
        request=request,
        decision="deny",
        reason=f"circuit open for agent_role='{request.agent_role}' change_id='{request.change_id}'",
        policy_version=policy_version,
        duration_ms=duration_ms,
        layer_failed="circuit",
        severity="SEV-2",
        model_id=request.model_id,
        vendor_family=vendor_family,
        deployment=deployment,
        error_type="CircuitOpenError",
    )
    runtime.audit_adapter.write_routing_decision(record)
    return _error_response(
        decision="deny",
        model_id=request.model_id,
        vendor_family=vendor_family,
        deployment=deployment,
        routing_log_id=routing_log_id,
        policy_version=policy_version,
        duration_ms=duration_ms,
        error_type="CircuitOpenError",
        message=record["reason"],
        layer_failed="circuit",
        severity="SEV-2",
    )


def route_v2(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = _runtime()
    started = time.perf_counter()
    try:
        request = _build_request(payload)
    except ValueError as exc:
        return _invalid_request_response(payload, message=str(exc), started=started)

    if runtime.circuit_breaker.is_open(request.agent_role, request.change_id):
        return _open_circuit_response(request, (time.perf_counter() - started) * 1000)

    try:
        allowlist = runtime.allowlist_for(request.change_id).get_allowlist()
    except AllowlistError as exc:
        routing_log_id = uuid.uuid4().hex
        policy_version = runtime.last_policy_version
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=str(exc),
            policy_version=policy_version,
            duration_ms=(time.perf_counter() - started) * 1000,
            layer_failed="allowlist",
            severity="WARN",
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            error_type="AllowlistError",
        )
        runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
        runtime.audit_adapter.write_routing_decision(record)
        return _error_response(
            decision="deny",
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            routing_log_id=routing_log_id,
            policy_version=policy_version,
            duration_ms=(time.perf_counter() - started) * 1000,
            error_type="AllowlistError",
            message=str(exc),
            layer_failed="allowlist",
            severity="WARN",
        )

    runtime.last_policy_version = allowlist.active_policy_version()
    entry = allowlist.lookup(request.model_id)
    routing_log_id = uuid.uuid4().hex
    if entry is None:
        reason = (
            f"model_id='{request.model_id}' not present in active allowlist "
            f"agent_role='{request.agent_role}' data_level='{request.data_level}'"
        )
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=reason,
            policy_version=allowlist.active_policy_version(),
            duration_ms=(time.perf_counter() - started) * 1000,
            layer_failed="allowlist",
            severity="WARN",
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            error_type="AllowlistError",
        )
        runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
        runtime.audit_adapter.write_routing_decision(record)
        return _error_response(
            decision="deny",
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            routing_log_id=routing_log_id,
            policy_version=allowlist.active_policy_version(),
            duration_ms=(time.perf_counter() - started) * 1000,
            error_type="AllowlistError",
            message=reason,
            layer_failed="allowlist",
            severity="WARN",
        )

    rate_limiter = runtime.rate_limiter_for(request.model_id, entry.rate_limit_qps)
    if not rate_limiter.acquire(request.agent_role, request.model_id):
        severity = "WARN"
        reason = (
            f"rate limit exceeded for model_id='{request.model_id}' "
            f"agent_role='{request.agent_role}' qps={entry.rate_limit_qps}"
        )
        event = runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
        if event is not None:
            severity = event.severity
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=reason,
            policy_version=allowlist.active_policy_version(),
            duration_ms=(time.perf_counter() - started) * 1000,
            layer_failed="rate",
            severity=severity,
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            error_type="RateLimitError",
        )
        runtime.audit_adapter.write_routing_decision(record)
        return _error_response(
            decision="deny",
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            routing_log_id=routing_log_id,
            policy_version=allowlist.active_policy_version(),
            duration_ms=(time.perf_counter() - started) * 1000,
            error_type="RateLimitError",
            message=reason,
            layer_failed="rate",
            severity=severity,
        )

    core = PolicyCore(
        allowlist,
        heterogeneity_check=runtime.heterogeneity_policy.check,
    )
    decision: RouteDecision = core.evaluate(request)

    elapsed_ms = (time.perf_counter() - started) * 1000
    if decision.decision == "deny":
        severity = "WARN"
        event = runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
        if event is not None:
            severity = event.severity
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=decision.reason,
            policy_version=decision.policy_version,
            duration_ms=elapsed_ms,
            layer_failed=decision.layer_failed,
            severity=severity,
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            error_type="PolicyDenyError",
        )
        runtime.audit_adapter.write_routing_decision(record)
        return _error_response(
            decision="deny",
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            routing_log_id=routing_log_id,
            policy_version=decision.policy_version,
            duration_ms=elapsed_ms,
            error_type="PolicyDenyError",
            message=decision.reason,
            layer_failed=str(decision.layer_failed or "policy"),
            severity=severity,
        )

    record = _audit_record(
        routing_log_id=routing_log_id,
        request=request,
        decision="allow",
        reason=decision.reason,
        policy_version=decision.policy_version,
        duration_ms=elapsed_ms,
        layer_failed=None,
        severity=None,
        model_id=request.model_id,
        vendor_family=entry.vendor_family,
        deployment=entry.deployment,
        error_type=None,
    )
    runtime.audit_adapter.write_routing_decision(record)
    return _base_response(
        decision="allow",
        model_id=request.model_id,
        vendor_family=entry.vendor_family,
        deployment=entry.deployment,
        routing_log_id=routing_log_id,
        policy_version=decision.policy_version,
        duration_ms=elapsed_ms,
    )


def health_v2() -> dict[str, Any]:
    runtime = _runtime()
    return {
        "status": "ok-v2",
        "policy_version": runtime.last_policy_version or "",
        "circuit_open_count": runtime.circuit_open_count(),
    }


def inject_allowlist(payload: dict[str, Any]) -> dict[str, Any]:
    """Token-gated helper for dev workflows; not used by route path."""
    token = os.environ.get("ALLOWLIST_INJECT_TOKEN")
    if not token:
        return {"error": "ALLOWLIST_INJECT_TOKEN not configured"}
    if payload.get("token") != token:
        return {"error": "token invalid"}

    change_id = payload.get("change_id")
    allowlist = payload.get("allowlist")
    if not isinstance(change_id, str) or not change_id:
        return {"error": "missing change_id"}
    if not isinstance(allowlist, dict):
        return {"error": "missing allowlist"}

    target = _allowlist_path(change_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(allowlist, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "injected", "path": str(target)}


def _dispatch_method(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "route":
        return route_v2(params)
    if method == "health":
        return health_v2()
    if method == "inject_allowlist":
        return inject_allowlist(params)
    return {"error": {"code": -32601, "message": "Method not found"}}


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                resp = {"id": None, "error": {"code": -32700, "message": str(exc)}}
            else:
                method = req.get("method")
                params = req.get("params", {})
                result = _dispatch_method(str(method), params if isinstance(params, dict) else {})
                if (
                    "error" in result
                    and isinstance(result["error"], dict)
                    and "code" in result["error"]
                ):
                    resp = {"id": req.get("id"), "error": result["error"]}
                else:
                    resp = {"id": req.get("id"), "result": result}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0

    cmd = sys.argv[1] if len(sys.argv) > 1 else "route"
    if cmd in {"route", "health", "inject_allowlist"}:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        if cmd == "health":
            result = health_v2()
        elif cmd == "inject_allowlist":
            result = inject_allowlist(payload if isinstance(payload, dict) else {})
        else:
            result = route_v2(payload if isinstance(payload, dict) else {})
        print(json.dumps(result, ensure_ascii=False))
        return 0

    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
