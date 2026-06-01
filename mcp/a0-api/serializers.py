from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CTX_VALUES = {"dev", "prod"}
GATE_GROUP_VALUES = {"compliance", "security"}
GATE_STATUS_VALUES = {"green", "yellow", "red", "planned"}
ALERT_LEVEL_VALUES = {"info", "warn", "crit"}
EVENT_STATUS_VALUES = {"green", "yellow", "red"}
SEC_TYPE_VALUES = {"注入", "滥用", "输出"}
DATA_LEVEL_VALUES = {"L2", "L3", "L4"}

_HEXISH_RE = re.compile(r"^[0-9a-fA-F]{32,}$")
_PLACEHOLDER_RE = re.compile(r"^__[A-Z]+_[a-z0-9]+__$")
_PHI_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cn_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("cn_phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("bank_card", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    ("cn_passport", re.compile(r"\b[EeGgDdSsPpHh]\d{8}\b")),
)


@dataclass(frozen=True)
class PhiViolation:
    path: str
    kind: str


class PhiLeakError(Exception):
    """Raised when a response violates the A0 0-PHI output contract."""

    def __init__(self, violations: list[PhiViolation], where: str | None = None) -> None:
        self.violations = violations
        label = f"({where})" if where else ""
        super().__init__(f"assert_no_phi{label}: {len(violations)} sanitized violation(s)")


def _scan_string(value: str) -> list[str]:
    if _HEXISH_RE.fullmatch(value):
        return []

    hits: list[str] = []
    for kind, pattern in _PHI_PATTERNS:
        for token in value.split():
            if _PLACEHOLDER_RE.fullmatch(token):
                continue
            if pattern.search(token):
                hits.append(kind)
                break
    return hits


def _walk(node: Any, path: str, out: list[PhiViolation]) -> None:
    if isinstance(node, str):
        for kind in _scan_string(node):
            out.append(PhiViolation(path=path, kind=kind))
        return

    if isinstance(node, list):
        for index, item in enumerate(node):
            _walk(item, f"{path}[{index}]", out)
        return

    if isinstance(node, dict):
        if "payload" in node and node["payload"] is not None:
            out.append(PhiViolation(path=f"{path}.payload", kind="payload_not_null"))
        for key, value in node.items():
            _walk(value, f"{path}.{key}", out)


def find_phi(value: Any) -> list[PhiViolation]:
    violations: list[PhiViolation] = []
    _walk(value, "$", violations)
    return violations


def assert_no_phi(value: dict[str, Any], where: str | None = None) -> dict[str, Any]:
    violations = find_phi(value)
    if violations:
        raise PhiLeakError(violations, where)
    return value


def _as_int(value: Any, default: int = 0, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _enum(value: Any, allowed: set[str], default: str) -> str:
    parsed = _as_str(value, default)
    return parsed if parsed in allowed else default


def _optional_str(record: dict[str, Any], key: str) -> dict[str, str]:
    value = record.get(key)
    if value is None:
        return {}
    return {key: _as_str(value)}


def serialize_posture(data: dict[str, Any]) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    for gate in data.get("gates") or []:
        if not isinstance(gate, dict):
            continue
        item: dict[str, Any] = {
            "id": _as_str(gate.get("id")),
            "group": _enum(gate.get("group"), GATE_GROUP_VALUES, "compliance"),
            "status": _enum(gate.get("status"), GATE_STATUS_VALUES, "planned"),
            "metric": _as_str(gate.get("metric")),
        }
        item.update(_optional_str(gate, "desc"))
        if "built" in gate:
            item["built"] = bool(gate.get("built"))
        gates.append(item)

    alerts: list[dict[str, Any]] = []
    for alert in data.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        alerts.append(
            {
                "cat": _enum(alert.get("cat"), GATE_GROUP_VALUES, "security"),
                "type": _as_str(alert.get("type"), "输出"),
                "level": _enum(alert.get("level"), ALERT_LEVEL_VALUES, "info"),
                "summary": _as_str(alert.get("summary")),
                "payload": None,
            }
        )

    response = {
        "composite": _as_int(data.get("composite"), maximum=100),
        "compliance_score": _as_int(data.get("compliance_score"), maximum=100),
        "security_score": _as_int(data.get("security_score"), maximum=100),
        "gates": gates,
        "alerts": alerts,
    }
    return assert_no_phi(response, "GET /posture")


def serialize_traffic(data: dict[str, Any]) -> dict[str, Any]:
    inbound = data.get("inbound") if isinstance(data.get("inbound"), dict) else {}
    gate = inbound.get("gate") if isinstance(inbound.get("gate"), dict) else {}
    outbound = data.get("outbound") if isinstance(data.get("outbound"), dict) else {}
    outbound_gate = outbound.get("gate") if isinstance(outbound.get("gate"), dict) else {}

    upstreams: list[dict[str, Any]] = []
    for upstream in inbound.get("upstreams") or []:
        if not isinstance(upstream, dict):
            continue
        upstreams.append(
            {
                "name": _as_str(upstream.get("name")),
                "ctx": _enum(upstream.get("ctx"), CTX_VALUES, "dev"),
                "rate": _as_int(upstream.get("rate")),
            }
        )

    downstream: list[dict[str, Any]] = []
    for node in inbound.get("downstream") or []:
        if not isinstance(node, dict):
            continue
        item = {"name": _as_str(node.get("name"))}
        item.update(_optional_str(node, "note"))
        downstream.append(item)

    response = {
        "inbound": {
            "upstreams": upstreams,
            "gate": {
                "hit": _as_int(gate.get("hit")),
                "blocked": _as_int(gate.get("blocked")),
                "passed": _as_int(gate.get("passed")),
            },
            "downstream": downstream,
        },
        "outbound": {
            "built": bool(outbound.get("built", False)),
            "gate": {
                "phi_reflow": _as_int(outbound_gate.get("phi_reflow")),
                "harmful": _as_int(outbound_gate.get("harmful")),
                "hallucination": _as_int(outbound_gate.get("hallucination")),
            },
        },
    }
    if outbound.get("note") is not None:
        response["outbound"]["note"] = _as_str(outbound.get("note"))
    return assert_no_phi(response, "GET /traffic")


def serialize_events(data: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        cat = _enum(event.get("cat"), {"comp", "sec"}, "comp")
        item: dict[str, Any] = {
            "ts": _as_str(event.get("ts")),
            "cat": cat,
            "status": _enum(event.get("status"), EVENT_STATUS_VALUES, "yellow"),
            "upstream": _as_str(event.get("upstream")),
            "ctx": _enum(event.get("ctx"), CTX_VALUES, "dev"),
            "action": _as_str(event.get("action")),
            "ref": _as_str(event.get("ref")),
        }
        if cat == "sec":
            item["sec_type"] = _enum(event.get("sec_type"), SEC_TYPE_VALUES, "输出")
            item["payload"] = None
        else:
            item["level"] = _enum(event.get("level"), DATA_LEVEL_VALUES, "L2")
        events.append(item)

    response = {"events": events}
    return assert_no_phi(response, "GET /events")
