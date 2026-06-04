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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent))
import tier_trust  # noqa: E402
from allowlist import AllowlistError, HotAllowlist  # noqa: E402
from heterogeneity import HeterogeneityPolicy  # noqa: E402
from limits import CircuitBreaker, RateLimiter  # noqa: E402
from policy import PolicyCore, RouteDecision, RouteRequest  # noqa: E402
from vendor_families import DEFAULT_VENDOR_FAMILIES_PATH, load_vendor_families  # noqa: E402

LOGGER = logging.getLogger(__name__)
VENDOR_FAMILIES_PATH = DEFAULT_VENDOR_FAMILIES_PATH
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 9000
DEFAULT_HTTP_MAX_BODY_BYTES = 1_048_576


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
    """Map model-router decisions into T4 audit events."""

    def __init__(self, audit_server: Any = None, audit_server_factory: Any = None) -> None:
        if audit_server is None and audit_server_factory is None:
            raise NotImplementedError(
                "ClickHouseAuditAdapter requires audit_server or audit_server_factory; "
                "v0.5.0 callers should explicitly inject AuditLogServerV2"
            )
        self._audit_server = audit_server
        self._audit_server_factory = audit_server_factory

    def write_routing_decision(self, record: dict[str, Any]) -> str:
        event = self._record_to_event(record)
        result = self._audit_server_instance().append(event)
        return str(result.get("event_id") or event["event_id"])

    def _audit_server_instance(self) -> Any:
        if self._audit_server is None:
            self._audit_server = self._audit_server_factory()
        return self._audit_server

    @staticmethod
    def _record_to_event(record: dict[str, Any]) -> dict[str, Any]:
        import hashlib
        from datetime import datetime, timezone

        routing_log_id = str(record.get("routing_log_id") or uuid.uuid4().hex)
        input_payload = (
            f"{record.get('model_id', '')}|"
            f"{record.get('change_id', '')}|"
            f"{record.get('data_level', '')}"
        )
        output_payload = f"{routing_log_id}|{record.get('decision', '')}|{record.get('reason', '')}"

        return {
            "event_id": routing_log_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": {
                "agent_role": str(record.get("agent_role", "")),
                "model_id": str(record.get("model_id", "")),
                "vendor_family": str(record.get("vendor_family", "")),
                "session_id": "",
            },
            "action": {
                "tool": "model-router",
                "skill": None,
                "operation": "route",
            },
            "context": {
                "change_id": str(record.get("change_id", "")),
                "step": None,
                "data_levels": [str(record.get("data_level", ""))],
            },
            "result": {
                "status": str(record.get("decision", "deny")),
                "reason": str(record.get("reason", "")),
                "duration_ms": float(record.get("duration_ms", 0.0)),
            },
            "input_hash": hashlib.sha256(input_payload.encode()).hexdigest(),
            "output_hash": hashlib.sha256(output_payload.encode()).hexdigest(),
        }


def _build_request(payload: dict[str, Any]) -> RouteRequest:
    required = ("model_id", "agent_role", "data_level", "change_id")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    # Tier fields are only trusted when signed by the gate middleware (B1 / ADR-18 §3).
    # Fail-closed: no secret or no/invalid signature => tier_trusted False => PolicyCore deny.
    secret = tier_trust.load_secret()
    metadata: dict[str, object] = {
        "desensitized": bool(payload.get("desensitized", False)),
        "tier_trusted": tier_trust.verify_tier(payload, payload.get("tier_sig"), secret),  # type: ignore[arg-type]
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


# H2: external error responses must NOT leak the internal policy reason / traces
# (model_id, agent_role, change_id, data_level values, circuit detail). The caller
# gets a stable code + generic message; the detailed reason stays only in the audit record.
_GENERIC_ERROR_MESSAGE = {
    "PolicyDenyError": "request denied by routing policy",
    "InvalidRequestError": "invalid routing request",
    "CircuitOpenError": "model temporarily unavailable",
    "RateLimitError": "rate limit exceeded",
    "AllowlistError": "request denied by routing policy",
}


def _external_message(error_type: str) -> str:
    return _GENERIC_ERROR_MESSAGE.get(error_type, "request denied")


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
    message: str,  # retained for the audit record / caller intent; NOT sent to the client (H2)
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
    error = {
        "type": error_type,
        "message": _external_message(error_type),
        "layer_failed": layer_failed,
    }
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


def _decision_payload(decision: RouteDecision) -> dict[str, object]:
    return {
        "decision": decision.decision,
        "reason": decision.reason,
        "layer_failed": decision.layer_failed,
        "policy_version": decision.policy_version,
        "duration_us": decision.duration_us,
        "allowed_model_set": list(decision.allowed_model_set),
        "lane": decision.lane,
        "max_data_level": decision.max_data_level,
        "map_id": decision.map_id,
    }


def _sign_decision_payload(payload: dict[str, object]) -> str | None:
    secret = tier_trust.load_secret()
    if secret is None:
        return None
    return tier_trust.sign_decision(payload, secret)


def _http_denied_response(*, routing_log_id: str, policy_version: str) -> dict[str, object]:
    return {
        "decision": "deny",
        "routing_log_id": routing_log_id,
        "policy_version": policy_version,
        "error": {
            "code": "route_denied",
            "msg": "request denied by routing policy",
        },
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


@dataclass(frozen=True)
class _RouteEvaluation:
    request: RouteRequest
    decision: RouteDecision
    routing_log_id: str
    model_id: str
    vendor_family: str
    deployment: str
    duration_ms: float
    error_type: str | None = None
    severity: str | None = None
    legacy_layer_failed: str | None = None


def _deny_decision(
    *,
    reason: str,
    layer_failed: Any,
    policy_version: str,
    started: float,
) -> RouteDecision:
    return RouteDecision(
        decision="deny",
        reason=reason,
        layer_failed=layer_failed,
        policy_version=policy_version,
        duration_us=max(0, int((time.perf_counter() - started) * 1_000_000)),
    )


def _evaluate_route(payload: dict[str, Any], *, started: float | None = None) -> _RouteEvaluation:
    runtime = _runtime()
    started = started or time.perf_counter()
    request = _build_request(payload)

    if runtime.circuit_breaker.is_open(request.agent_role, request.change_id):
        duration_ms = (time.perf_counter() - started) * 1000
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
        reason = (
            f"circuit open for agent_role='{request.agent_role}' "
            f"change_id='{request.change_id}'"
        )
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=reason,
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
        return _RouteEvaluation(
            request=request,
            decision=_deny_decision(
                reason=reason,
                layer_failed="circuit",
                policy_version=policy_version,
                started=started,
            ),
            routing_log_id=routing_log_id,
            model_id=request.model_id,
            vendor_family=vendor_family,
            deployment=deployment,
            duration_ms=duration_ms,
            error_type="CircuitOpenError",
            severity="SEV-2",
            legacy_layer_failed="circuit",
        )

    try:
        allowlist = runtime.allowlist_for(request.change_id).get_allowlist()
    except AllowlistError as exc:
        routing_log_id = uuid.uuid4().hex
        policy_version = runtime.last_policy_version
        duration_ms = (time.perf_counter() - started) * 1000
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=str(exc),
            policy_version=policy_version,
            duration_ms=duration_ms,
            layer_failed="allowlist",
            severity="WARN",
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            error_type="AllowlistError",
        )
        runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
        runtime.audit_adapter.write_routing_decision(record)
        return _RouteEvaluation(
            request=request,
            decision=_deny_decision(
                reason=str(exc),
                layer_failed="allowlist",
                policy_version=policy_version,
                started=started,
            ),
            routing_log_id=routing_log_id,
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            duration_ms=(time.perf_counter() - started) * 1000,
            error_type="AllowlistError",
            severity="WARN",
            legacy_layer_failed="allowlist",
        )

    runtime.last_policy_version = allowlist.active_policy_version()
    entry = allowlist.lookup(request.model_id)
    routing_log_id = uuid.uuid4().hex
    if entry is None:
        reason = (
            f"model_id='{request.model_id}' not present in active allowlist "
            f"agent_role='{request.agent_role}' data_level='{request.data_level}'"
        )
        duration_ms = (time.perf_counter() - started) * 1000
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=reason,
            policy_version=allowlist.active_policy_version(),
            duration_ms=duration_ms,
            layer_failed="allowlist",
            severity="WARN",
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            error_type="AllowlistError",
        )
        runtime.circuit_breaker.record_reject(request.agent_role, request.change_id)
        runtime.audit_adapter.write_routing_decision(record)
        return _RouteEvaluation(
            request=request,
            decision=_deny_decision(
                reason=reason,
                layer_failed="allowlist",
                policy_version=allowlist.active_policy_version(),
                started=started,
            ),
            routing_log_id=routing_log_id,
            model_id=request.model_id,
            vendor_family="",
            deployment="",
            duration_ms=duration_ms,
            error_type="AllowlistError",
            severity="WARN",
            legacy_layer_failed="allowlist",
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
        duration_ms = (time.perf_counter() - started) * 1000
        record = _audit_record(
            routing_log_id=routing_log_id,
            request=request,
            decision="deny",
            reason=reason,
            policy_version=allowlist.active_policy_version(),
            duration_ms=duration_ms,
            layer_failed="rate",
            severity=severity,
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            error_type="RateLimitError",
        )
        runtime.audit_adapter.write_routing_decision(record)
        return _RouteEvaluation(
            request=request,
            decision=_deny_decision(
                reason=reason,
                layer_failed="rate",
                policy_version=allowlist.active_policy_version(),
                started=started,
            ),
            routing_log_id=routing_log_id,
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            duration_ms=duration_ms,
            error_type="RateLimitError",
            severity=severity,
            legacy_layer_failed="rate",
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
        return _RouteEvaluation(
            request=request,
            decision=decision,
            routing_log_id=routing_log_id,
            model_id=request.model_id,
            vendor_family=entry.vendor_family,
            deployment=entry.deployment,
            duration_ms=elapsed_ms,
            error_type="PolicyDenyError",
            severity=severity,
            legacy_layer_failed=str(decision.layer_failed or "policy"),
        )

    record = _audit_record(
        routing_log_id=routing_log_id,
        request=request,
        decision=decision.decision,
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
    return _RouteEvaluation(
        request=request,
        decision=decision,
        routing_log_id=routing_log_id,
        model_id=request.model_id,
        vendor_family=entry.vendor_family,
        deployment=entry.deployment,
        duration_ms=elapsed_ms,
    )


def _legacy_route_response(evaluation: _RouteEvaluation) -> dict[str, Any]:
    if evaluation.decision.decision == "deny":
        return _error_response(
            decision="deny",
            model_id=evaluation.model_id,
            vendor_family=evaluation.vendor_family,
            deployment=evaluation.deployment,
            routing_log_id=evaluation.routing_log_id,
            policy_version=evaluation.decision.policy_version,
            duration_ms=evaluation.duration_ms,
            error_type=evaluation.error_type or "PolicyDenyError",
            message=evaluation.decision.reason,
            layer_failed=evaluation.legacy_layer_failed
            or str(evaluation.decision.layer_failed or "policy"),
            severity=evaluation.severity,
        )

    return _base_response(
        decision=evaluation.decision.decision,
        model_id=evaluation.model_id,
        vendor_family=evaluation.vendor_family,
        deployment=evaluation.deployment,
        routing_log_id=evaluation.routing_log_id,
        policy_version=evaluation.decision.policy_version,
        duration_ms=evaluation.duration_ms,
    )


def route_v2(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        evaluation = _evaluate_route(payload, started=started)
    except ValueError as exc:
        return _invalid_request_response(payload, message=str(exc), started=started)
    return _legacy_route_response(evaluation)


def route_http(payload: dict[str, Any]) -> dict[str, object]:
    started = time.perf_counter()
    try:
        evaluation = _evaluate_route(payload, started=started)
    except ValueError as exc:
        denied = _invalid_request_response(payload, message=str(exc), started=started)
        return _http_denied_response(
            routing_log_id=str(denied.get("routing_log_id", "")),
            policy_version=str(denied.get("policy_version", "")),
        )

    if evaluation.decision.decision == "deny":
        return _http_denied_response(
            routing_log_id=evaluation.routing_log_id,
            policy_version=evaluation.decision.policy_version,
        )

    decision_payload = _decision_payload(evaluation.decision)
    signature = _sign_decision_payload(decision_payload)
    if signature is None:
        raise RuntimeError("decision signing unavailable")
    return {
        **decision_payload,
        "sig": signature,
        "routing_log_id": evaluation.routing_log_id,
        "model_id": evaluation.model_id,
        "vendor_family": evaluation.vendor_family,
        "deployment": evaluation.deployment,
        "_meta": {"duration_ms": round(evaluation.duration_ms, 3)},
    }


class _ModelRouterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class _ModelRouterHTTPHandler(BaseHTTPRequestHandler):
    server_version = "MedHarnessModelRouterHTTP"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "msg": message}})

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            raise ValueError("missing content length")
        try:
            content_length = int(length_header)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length < 0 or content_length > DEFAULT_HTTP_MAX_BODY_BYTES:
            raise ValueError("request body too large")
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            raise ValueError("request body truncated")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _handle_health(self) -> None:
        self._send_json(HTTPStatus.OK, health_v2())

    def _handle_route(self) -> None:
        try:
            payload = self._read_json_body()
        except Exception:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return

        try:
            response = route_http(payload)
        except Exception:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "model_router_failed_closed",
                "model-router failed closed",
            )
            return

        self._send_json(HTTPStatus.OK, response)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._handle_health()
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/route":
            self._handle_route()
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _parse_serve_args(argv: list[str]) -> tuple[str, int]:
    host = DEFAULT_HTTP_HOST
    port = DEFAULT_HTTP_PORT
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--http":
            index += 1
            continue
        if arg == "--host":
            if index + 1 >= len(argv):
                raise ValueError("--host requires a value")
            host = argv[index + 1]
            index += 2
            continue
        if arg == "--port":
            if index + 1 >= len(argv):
                raise ValueError("--port requires a value")
            try:
                port = int(argv[index + 1])
            except ValueError as exc:
                raise ValueError("invalid --port value") from exc
            index += 2
            continue
        raise ValueError(f"unknown serve option: {arg}")
    return host, port


def _serve_http(host: str, port: int) -> int:
    server = _ModelRouterHTTPServer((host, port), _ModelRouterHTTPHandler)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


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
    if len(sys.argv) > 1 and sys.argv[1] == "serve" and "--http" in sys.argv[2:]:
        try:
            host, port = _parse_serve_args(sys.argv[2:])
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
        return _serve_http(host, port)

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
