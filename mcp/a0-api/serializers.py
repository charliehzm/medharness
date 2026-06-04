from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

CTX_VALUES = {"dev", "prod"}
GATE_GROUP_VALUES = {"compliance", "security"}
GATE_STATUS_VALUES = {"green", "yellow", "red", "planned"}
ALERT_LEVEL_VALUES = {"info", "warn", "crit"}
EVENT_STATUS_VALUES = {"green", "yellow", "red"}
SEC_TYPE_VALUES = {"注入", "滥用", "输出"}
DATA_LEVEL_VALUES = {"L2", "L3", "L4"}
TOKEN_STATUS_VALUES = {"enabled", "disabled", "throttled"}
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
# Patient-PHI patterns = the full PHI set MINUS email. Rationale: on the staff
# user-management view a staff operator's *work* email is identity metadata, not
# patient PHI — it is allowed to surface. A patient identifier (id card, mobile,
# bank card, passport) must NEVER appear there, so we keep every patient pattern
# and only drop the email one. The gateway/audit data path is unchanged and still
# enforces the full 0-PHI contract via assert_no_phi (email included).
_PATIENT_PHI_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, pattern) for kind, pattern in _PHI_PATTERNS if kind != "email"
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


def _scan_string(
    value: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = _PHI_PATTERNS,
) -> list[str]:
    if _HEXISH_RE.fullmatch(value):
        return []

    hits: list[str] = []
    for kind, pattern in patterns:
        for token in value.split():
            if _PLACEHOLDER_RE.fullmatch(token):
                continue
            if pattern.search(token):
                hits.append(kind)
                break
    return hits


def _walk(
    node: Any,
    path: str,
    out: list[PhiViolation],
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = _PHI_PATTERNS,
) -> None:
    if isinstance(node, str):
        for kind in _scan_string(node, patterns):
            out.append(PhiViolation(path=path, kind=kind))
        return

    if isinstance(node, list):
        for index, item in enumerate(node):
            _walk(item, f"{path}[{index}]", out, patterns)
        return

    if isinstance(node, dict):
        if "payload" in node and node["payload"] is not None:
            out.append(PhiViolation(path=f"{path}.payload", kind="payload_not_null"))
        for key, value in node.items():
            _walk(value, f"{path}.{key}", out, patterns)


def find_phi(value: Any) -> list[PhiViolation]:
    violations: list[PhiViolation] = []
    _walk(value, "$", violations)
    return violations


def assert_no_phi(value: dict[str, Any], where: str | None = None) -> dict[str, Any]:
    violations = find_phi(value)
    if violations:
        raise PhiLeakError(violations, where)
    return value


def find_patient_phi(value: Any) -> list[PhiViolation]:
    violations: list[PhiViolation] = []
    _walk(value, "$", violations, _PATIENT_PHI_PATTERNS)
    return violations


def assert_no_patient_phi(value: dict[str, Any], where: str | None = None) -> dict[str, Any]:
    """Like ``assert_no_phi`` but tolerant of staff email (patient PHI only).

    Used by the staff user-management serializer: a staff operator's work email is
    identity metadata and may surface, but a patient identifier (cn id / mobile /
    bank card / passport) must never leak even if upstream injected one. Raises the
    same ``PhiLeakError`` as ``assert_no_phi`` so callers handle one error type.
    """
    violations = find_patient_phi(value)
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


def _items_from(data: Any, key: str) -> list[Any]:
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return data["items"]
        if isinstance(data.get(key), list):
            return data[key]
    if isinstance(data, list):
        return data
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in re.split(r"[,;\s]+", value) if item.strip()]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    for item in raw_items:
        text = _as_str(item).strip()
        if text:
            out.append(text)
    return out


def _channel_status_label(value: Any) -> str:
    if isinstance(value, bool):
        return "green" if value else "yellow"
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        text = _as_str(value)
        if text in EVENT_STATUS_VALUES:
            return text
        if text in {"enabled", "active"}:
            return "green"
        if text in {"disabled", "inactive"}:
            return "yellow"
        return "yellow"
    if parsed == 1:
        return "green"
    if parsed <= 0:
        return "red"
    return "yellow"


def _token_status_label(value: Any) -> str:
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        text = _as_str(value)
        return text if text in TOKEN_STATUS_VALUES else "disabled"
    return "enabled" if parsed == 1 else "disabled"


def _channel_region(channel: dict[str, Any], models: list[str]) -> str:
    explicit = _as_str(channel.get("region"))
    if explicit:
        return explicit
    haystack = " ".join(models + [_as_str(channel.get("group"))]).lower()
    if any(hint in haystack for hint in ("claude", "gpt", "境外")):
        return "境外·仅脱敏"
    return "境内"


def _channel_lane(channel: dict[str, Any], models: list[str]) -> str:
    explicit = _as_str(channel.get("lane"))
    if explicit in LANE_VALUES:
        return explicit
    haystack = " ".join(models + [_as_str(channel.get("group")), _as_str(channel.get("name"))]).lower()
    if any(hint in haystack for hint in ("sensitive", "l3", "l4", "phi", "private", "敏感")):
        return "sensitive"
    return "normal"


def _token_allowed_data_levels(token: dict[str, Any]) -> list[str]:
    explicit = [
        _as_str(level)
        for level in _string_list(token.get("allowed_data_levels"))
        if _as_str(level) in DATA_LEVEL_VALUES
    ]
    if explicit:
        return explicit
    model_limits = token.get("model_limits")
    if isinstance(model_limits, dict):
        model_values = " ".join(str(v) for v in model_limits.values())
        model_text = f"{' '.join(model_limits.keys())} {model_values}"
    else:
        model_text = " ".join(_string_list(model_limits))
    haystack = f"{model_text} {_as_str(token.get('group'))}".lower()
    levels = {"L2"}
    if model_text or any(
        hint in haystack
        for hint in ("l3", "prod", "production", "default", "medical", "sensitive", "phi", "claude", "gpt")
    ):
        levels.add("L3")
    if "l4" in haystack:
        levels.add("L4")
    return [level for level in ("L2", "L3", "L4") if level in levels]


def serialize_admin_users(data: dict[str, Any]) -> dict[str, Any]:
    users: list[dict[str, Any]] = []
    for user in _items_from(data, "users"):
        if not isinstance(user, dict):
            continue
        console_role = user.get("console_role")
        if console_role is None:
            try:
                console_role = "系统管理员" if int(user.get("role")) >= 10 else None
            except (TypeError, ValueError):
                console_role = None
        users.append(
            {
                "id_hash": _id_hash(user, "u"),
                "role": _mgmt_role_label(user.get("role")),
                "status": _mgmt_status_label(user.get("status")),
                "group": _as_str(user.get("group")),
                "quota": _as_str(user.get("quota")),
                "used_quota": _as_str(user.get("used_quota")),
                "console_role": console_role if console_role in CONSOLE_ROLE_VALUES else None,
            }
        )

    response = {"users": users}
    return assert_no_phi(response, "GET /admin/users")


_MGMT_ROLE_LABELS = {100: "root", 10: "admin", 1: "normal"}
_MGMT_STATUS_LABELS = {1: "enabled", 2: "disabled"}


def _mgmt_role_label(value: Any) -> str:
    try:
        return _MGMT_ROLE_LABELS.get(int(value), str(int(value)))
    except (TypeError, ValueError):
        return _as_str(value)


def _mgmt_status_label(value: Any) -> str:
    try:
        return _MGMT_STATUS_LABELS.get(int(value), str(int(value)))
    except (TypeError, ValueError):
        return _as_str(value)


def _mgmt_last_login(value: Any) -> str:
    epoch = _as_int(value, default=0)
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_admin_users_mgmt(data: dict[str, Any]) -> dict[str, Any]:
    """Serialize new-api's user-list into the A0 management-view contract.

    Accepts new-api's ``{items:[...], total}`` shape OR a bare list. Whitelists ONLY
    the management fields below — password / access_token / oauth ids are never
    emitted — and maps the raw role/status ints to labels. Staff email is allowed
    here (operator identity, not patient PHI), so the result is gated by
    ``assert_no_patient_phi``: an injected patient identifier still throws.
    """
    items = data.get("items") if isinstance(data, dict) else None
    if items is None and isinstance(data, dict):
        items = data.get("users")
    if items is None:
        items = data if isinstance(data, list) else []

    users: list[dict[str, Any]] = []
    for user in items or []:
        if not isinstance(user, dict):
            continue
        # new-api's GetAllUsers is Unscoped — it returns soft-deleted accounts too. A
        # deleted staff account must leave the active management list (the record is kept
        # soft-deleted upstream for audit, but the Console only shows live operators).
        # gorm.DeletedAt has no json tag, so it marshals as "DeletedAt" (a timestamp when
        # set, null when live); accept the snake_case form too in case marshaling changes.
        if user.get("DeletedAt") or user.get("deleted_at"):
            continue
        users.append(
            {
                "id": _as_int(user.get("id")),
                "username": _as_str(user.get("username")),
                "display_name": _as_str(user.get("display_name")),
                "email": _as_str(user.get("email")),
                "role": _mgmt_role_label(user.get("role")),
                "status": _mgmt_status_label(user.get("status")),
                "group": _as_str(user.get("group")),
                "quota": _as_str(user.get("quota")),
                "used_quota": _as_str(user.get("used_quota")),
                "last_login": _mgmt_last_login(
                    user.get("last_login_time", user.get("last_login"))
                ),
            }
        )

    # Upstream total is an Unscoped count (includes soft-deleted); the active list is
    # what we actually return, so report its length.
    response = {"users": users, "total": len(users)}
    return assert_no_patient_phi(response, "GET /admin/users/manage_list")


def serialize_admin_tokens(data: dict[str, Any]) -> dict[str, Any]:
    tokens: list[dict[str, Any]] = []
    for token in _items_from(data, "tokens"):
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
    for channel in _items_from(data, "channels"):
        if not isinstance(channel, dict):
            continue
        models = _string_list(channel.get("models"))
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


def serialize_admin_channels_mgmt(data: Any) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    for channel in _items_from(data, "channels"):
        if not isinstance(channel, dict):
            continue
        models = _string_list(channel.get("models"))
        channels.append(
            {
                "id": _as_int(channel.get("id")),
                "name": _as_str(channel.get("name")),
                "type": _as_str(channel.get("type")),
                "status": _channel_status_label(channel.get("status")),
                "weight": _as_int(channel.get("weight"), maximum=100),
                "models": models,
                "group": _as_str(channel.get("group")),
                "region": _channel_region(channel, models),
                "lane": _channel_lane(channel, models),
                "used_quota": _as_str(channel.get("used_quota")),
            }
        )

    response = {"channels": channels}
    return assert_no_phi(response, "GET /admin/channels")


def serialize_admin_tokens_mgmt(data: Any) -> dict[str, Any]:
    tokens: list[dict[str, Any]] = []
    for token in _items_from(data, "tokens"):
        if not isinstance(token, dict):
            continue
        tokens.append(
            {
                "id": _as_int(token.get("id")),
                "name": _as_str(token.get("name")),
                "status": _token_status_label(token.get("status")),
                "remain_quota": _as_str(token.get("remain_quota")),
                "unlimited_quota": bool(token.get("unlimited_quota")),
                "used_quota": _as_str(token.get("used_quota")),
                "group": _as_str(token.get("group")),
                "allowed_data_levels": _token_allowed_data_levels(token),
                "expired_time": _as_str(token.get("expired_time")),
                "accessed_time": _as_str(token.get("accessed_time")),
            }
        )

    response = {"tokens": tokens}
    return assert_no_phi(response, "GET /admin/tokens")


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

    goals: list[dict[str, Any]] = []
    for goal in data.get("goals") or []:
        if not isinstance(goal, dict):
            continue
        goals.append(
            {
                "key": _enum(goal.get("key"), {"security", "cost", "compliance", "stability"}, "security"),
                "score": _as_int(goal.get("score"), maximum=100),
                "metric": _as_str(goal.get("metric")),
                "submetric": _as_str(goal.get("submetric")),
                "summary": _as_str(goal.get("summary")),
            }
        )

    summaries_src = data.get("summaries") if isinstance(data.get("summaries"), dict) else {}
    summaries = {
        "security": _as_str(summaries_src.get("security")),
        "cost": _as_str(summaries_src.get("cost")),
    }

    response = {
        "composite": _as_int(data.get("composite"), maximum=100),
        "compliance_score": _as_int(data.get("compliance_score"), maximum=100),
        "security_score": _as_int(data.get("security_score"), maximum=100),
        "cost_score": _as_int(data.get("cost_score"), maximum=100),
        "stability_score": _as_int(data.get("stability_score"), maximum=100),
        "goals": goals,
        "summaries": summaries,
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
