from __future__ import annotations

import hashlib
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
CONFIG_SECTION_VALUES = {
    "scene",
    "models",
    "fields",
    "thresholds",
    "retention",
    "injection",
    "output",
    "quota",
    "upstream",
    "approval",
}
APPROVAL_LEVEL_VALUES = {"单签", "会签", "三签"}
CONSOLE_ROLE_VALUES = {"研发负责人", "系统管理员"}
LANE_VALUES = {"normal", "sensitive"}

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


def _id_hash(record: dict[str, Any], prefix: str) -> str:
    for key in ("id", "user_id", "token_id", "channel_id", "id_hash"):
        value = record.get(key)
        if value is not None:
            digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:6]
            return f"{prefix}#{digest}"
    return f"{prefix}#000000"


def _kv_items(value: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        items.append({"k": _as_str(item.get("k")), "v": _as_str(item.get("v"))})
    return items


def serialize_admin_users(data: dict[str, Any]) -> dict[str, Any]:
    users: list[dict[str, Any]] = []
    for user in data.get("users") or []:
        if not isinstance(user, dict):
            continue
        console_role = user.get("console_role")
        users.append(
            {
                "id_hash": _id_hash(user, "u"),
                "role": _as_str(user.get("role")),
                "status": _as_str(user.get("status")),
                "group": _as_str(user.get("group")),
                "quota": _as_str(user.get("quota")),
                "used_quota": _as_str(user.get("used_quota")),
                "console_role": console_role if console_role in CONSOLE_ROLE_VALUES else None,
            }
        )

    response = {"users": users}
    return assert_no_phi(response, "GET /admin/users")


def serialize_admin_tokens(data: dict[str, Any]) -> dict[str, Any]:
    tokens: list[dict[str, Any]] = []
    for token in data.get("tokens") or []:
        if not isinstance(token, dict):
            continue
        allowed_data_levels = [
            _enum(level, DATA_LEVEL_VALUES, "L2")
            for level in token.get("allowed_data_levels") or []
            if _as_str(level) in DATA_LEVEL_VALUES
        ]
        if not allowed_data_levels:
            allowed_data_levels = ["L2"]
        tokens.append(
            {
                "id_hash": _id_hash(token, "tk"),
                "name": _as_str(token.get("name")),
                "status": _as_str(token.get("status")),
                "remain_quota": _as_str(token.get("remain_quota")),
                "used_quota": _as_str(token.get("used_quota")),
                "allowed_data_levels": allowed_data_levels,
            }
        )

    response = {"tokens": tokens}
    return assert_no_phi(response, "GET /admin/tokens")


def serialize_admin_channels(data: dict[str, Any]) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    for channel in data.get("channels") or []:
        if not isinstance(channel, dict):
            continue
        models = [
            _as_str(model)
            for model in channel.get("models") or []
            if _as_str(model)
        ]
        channels.append(
            {
                "id_hash": _id_hash(channel, "ch"),
                "name": _as_str(channel.get("name")),
                "type": _as_str(channel.get("type")),
                "status": _enum(channel.get("status"), EVENT_STATUS_VALUES, "yellow"),
                "weight": _as_int(channel.get("weight"), maximum=100),
                "region": _as_str(channel.get("region")),
                "lane": _enum(channel.get("lane"), LANE_VALUES, "normal"),
                "models": models,
            }
        )

    response = {"channels": channels}
    return assert_no_phi(response, "GET /admin/channels")


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


def serialize_audit_lineage(data: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    for node in data.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        nodes.append(
            {
                "ico": _as_str(node.get("ico")),
                "t": _as_str(node.get("t")),
                "s": _as_str(node.get("s")),
            }
        )

    response = {
        "ref": _as_str(data.get("ref")),
        "title": _as_str(data.get("title")),
        "nodes": nodes,
        "hash": _as_str(data.get("hash")),
        "details": _kv_items(data.get("details")),
    }
    return assert_no_phi(response, "GET /audit/{ref}")


def serialize_upstreams(data: dict[str, Any]) -> dict[str, Any]:
    upstreams: list[dict[str, Any]] = []
    for upstream in data.get("upstreams") or []:
        if not isinstance(upstream, dict):
            continue
        upstreams.append(
            {
                "name": _as_str(upstream.get("name")),
                "ctx": _enum(upstream.get("ctx"), CTX_VALUES, "dev"),
                "protocol": _as_str(upstream.get("protocol"), "openai"),
                "status": _enum(upstream.get("status"), EVENT_STATUS_VALUES, "yellow"),
                "traffic_today": _as_int(upstream.get("traffic_today")),
                "phi": _as_str(upstream.get("phi")),
            }
        )

    response = {"upstreams": upstreams}
    return assert_no_phi(response, "GET /upstreams")


def serialize_config_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {
        "section": _enum(data.get("section"), CONFIG_SECTION_VALUES, "scene"),
        "title": _as_str(data.get("title")),
        "fields": _kv_items(data.get("fields")),
    }
    if "built" in data:
        response["built"] = bool(data.get("built"))
    if data.get("note") is not None:
        response["note"] = _as_str(data.get("note"))
    return assert_no_phi(response, "GET /config/{section}")


def serialize_cost(data: dict[str, Any]) -> dict[str, Any]:
    kpi_src = data.get("kpi") if isinstance(data.get("kpi"), dict) else {}
    kpi = {
        "month_cost": _as_str(kpi_src.get("month_cost")),
        "saved_vs_direct": _as_str(kpi_src.get("saved_vs_direct")),
        "saved_ratio": _as_str(kpi_src.get("saved_ratio")),
        "cache_hit_ratio": _as_str(kpi_src.get("cache_hit_ratio")),
        "cache_saved": _as_str(kpi_src.get("cache_saved")),
        "cap_day": _as_str(kpi_src.get("cap_day")),
        "cap_used": _as_str(kpi_src.get("cap_used")),
        "cap_left_ratio": _as_str(kpi_src.get("cap_left_ratio")),
        "normal_lane_ratio": _as_str(kpi_src.get("normal_lane_ratio")),
    }

    def by_dim(value: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in value or []:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "name": _as_str(item.get("name")),
                    "color_token": _as_str(item.get("color_token")),
                    "pct": _as_int(item.get("pct"), maximum=100),
                    "amount": _as_str(item.get("amount")),
                }
            )
        return items

    tips: list[dict[str, str]] = []
    for item in data.get("tips") or []:
        if not isinstance(item, dict):
            continue
        tips.append({"tip": _as_str(item.get("tip")), "saving": _as_str(item.get("saving"))})

    response = {
        "window": _enum(data.get("window"), {"1h", "24h", "7d", "month"}, "month"),
        "kpi": kpi,
        "by_lane": by_dim(data.get("by_lane")),
        "by_model": by_dim(data.get("by_model")),
        "trend": [_as_int(value) for value in data.get("trend") or []],
        "tips": tips,
    }
    return assert_no_phi(response, "GET /cost")


def serialize_channels(data: dict[str, Any]) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    for channel in data.get("channels") or []:
        if not isinstance(channel, dict):
            continue
        channels.append(
            {
                "name": _as_str(channel.get("name")),
                "model": _as_str(channel.get("model")),
                "weight": _as_int(channel.get("weight"), maximum=100),
                "unit_price": _as_str(channel.get("unit_price")),
                "p95_ms": _as_int(channel.get("p95_ms")),
                "region": _as_str(channel.get("region")),
                "picked": bool(channel.get("picked")),
                "status": _enum(channel.get("status"), EVENT_STATUS_VALUES, "yellow"),
            }
        )

    response = {"channels": channels}
    return assert_no_phi(response, "GET /channels")


def serialize_audit_export(data: dict[str, Any]) -> dict[str, Any]:
    response = {
        "bundle_id": _as_str(data.get("bundle_id")),
        "status": _enum(data.get("status"), {"packing", "ready"}, "packing"),
        "sha256": _as_str(data.get("sha256")),
    }
    return assert_no_phi(response, "POST /audit/export")


def serialize_config_propose(data: dict[str, Any]) -> dict[str, Any]:
    response = {
        "approval_id": _as_str(data.get("approval_id")),
        "level": _enum(data.get("level"), APPROVAL_LEVEL_VALUES, "会签"),
        "status": "queued",
    }
    return assert_no_phi(response, "POST /config/{section}/propose")
