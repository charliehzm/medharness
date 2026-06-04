"""A0 contract-conformance: live A0 responses must match the FROZEN FE contract.

The fixtures under web/src/api/contract/fixtures/*.json are exactly what the FE
renders against in mock mode (imported by web/src/api/contract/mock.ts). They are
therefore the single shared oracle for the FE<->BE seam. This test drives every
A0 endpoint with synthetic data (FakeClickHouse — no real infra, no real PHI) and
asserts each live response:

  1. returns HTTP 200,
  2. passes A0's own 0-PHI deep-scan guard (serializers.assert_no_phi),
  3. structurally conforms to the frozen fixture (same shape across variants).

A mismatch here is an FE<->BE seam drift that would break the M3 mock->live
cutover; triage it (fix BE serializer, fix FE contract, or relax an over-strict
fixture) until this is green.
"""

from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"
FIXTURES = ROOT / "web" / "src" / "api" / "contract" / "fixtures"

sys.path.insert(0, str(A0_DIR))

_spec = util.spec_from_file_location("a0_api_app_conformance", A0_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
a0_api_app = util.module_from_spec(_spec)
sys.modules["a0_api_app_conformance"] = a0_api_app
_spec.loader.exec_module(a0_api_app)

import serializers  # noqa: E402,I001


# --- synthetic ClickHouse (mirrors tests/test_a0_api.py; no real infra / PHI) ---
def _audit_rows() -> list[dict[str, object]]:
    base = {
        "actor_agent_role": "coder",
        "actor_vendor_family": "alibaba",
        "actor_session_id": "session-1",
        "action_skill": None,
        "context_change_id": "change-1",
        "context_step": 6,
        "context_data_levels": ["L3"],
        "result_duration_ms": 12.5,
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
        "prev_hash": "c" * 64,
    }
    return [
        {
            **base,
            "event_id": "evt-0001",
            "timestamp": "2026-05-29T08:12:03Z",
            "actor_model_id": "qwen-max-2026",
            "action_tool": "model-router",
            "action_operation": "route",
            "result_status": "success",
            "result_reason": "脱敏后路由 qwen-max",
            "current_hash": "routing#a1b2",
            "row_id": 1,
        },
        {
            **base,
            "event_id": "evt-0002",
            "timestamp": "2026-05-29T08:15:41Z",
            "actor_model_id": "dify-rag",
            "actor_vendor_family": "openai",
            "action_tool": "prompt-injection-scan",
            "action_operation": "detect",
            "result_status": "blocked",
            "result_reason": "检索内容含可疑指令→隔离",
            "current_hash": "inj#c3d4",
            "row_id": 2,
        },
    ]


class FakeClickHouse:
    def __init__(self) -> None:
        self.rows = _audit_rows()

    def query(self, sql: str) -> list[dict[str, object]]:
        if sql.startswith("INSERT INTO _audit_log FORMAT JSONEachRow"):
            self.rows.append(json.loads(sql.split("\n", 1)[1]))
            return []
        if "SELECT current_hash, row_id FROM _audit_log" in sql:
            if not self.rows:
                return []
            row = self.rows[-1]
            return [{"current_hash": row["current_hash"], "row_id": row["row_id"]}]
        return list(self.rows)


@pytest.fixture()
def a0_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(a0_api_app, "_query_clickhouse", FakeClickHouse().query)
    monkeypatch.setattr(a0_api_app, "_new_api_admin_request", _fake_new_api_admin_request)
    return a0_api_app.make_test_client(a0_api_app.app)


def _fake_new_api_admin_request(method: str, path: str, body: dict | None = None):
    if method == "GET" and path.startswith("/api/data/"):
        return 200, {"success": True, "data": []}
    if method == "GET" and path.startswith("/api/user/"):
        return 200, {
            "success": True,
            "data": {
                "items": [
                    {
                        "id": 1,
                        "role": 10,
                        "status": 1,
                        "group": "mgmt",
                        "quota": "—",
                        "used_quota": "¥12",
                    }
                ]
            },
        }
    if method == "GET" and path.startswith("/api/token/"):
        return 200, {
            "success": True,
            "data": {
                "items": [
                    {
                        "id": 10,
                        "name": "tk-synthetic",
                        "status": 1,
                        "remain_quota": 1000,
                        "unlimited_quota": False,
                        "used_quota": 10,
                        "group": "prod",
                        "model_limits": ["gpt-4o"],
                        "expired_time": -1,
                        "accessed_time": 1710000000,
                        "key": "sk-do-not-return",
                        "user_id": 1,
                    }
                ]
            },
        }
    if method == "GET" and path.startswith("/api/channel/"):
        return 200, {
            "success": True,
            "data": {
                "items": [
                    {
                        "id": 20,
                        "name": "Synthetic Channel",
                        "type": "openai",
                        "status": 1,
                        "weight": 80,
                        "models": ["gpt-4o"],
                        "group": "sensitive",
                        "used_quota": 12,
                        "key": "sk-do-not-return",
                        "base_url": "https://channel.example.invalid/private",
                    }
                ]
            },
        }
    return 200, {"success": True}


# --- endpoint table: (key, method, path, body, fixture) -----------------------
# Paths are API_BASE (/api/v1)-prefixed; the audit ref "#" is %23-encoded exactly
# as web/src/api/contract buildPath(encodeURIComponent) would send it.
ENDPOINTS = [
    ("posture", "GET", "/api/v1/posture", None, "posture.json"),
    ("traffic", "GET", "/api/v1/traffic", None, "traffic.json"),
    ("events", "GET", "/api/v1/events", None, "events.json"),
    ("audit", "GET", "/api/v1/audit/routing%23a1b2", None, "audit.json"),
    ("upstreams", "GET", "/api/v1/upstreams", None, "upstreams.json"),
    ("cost", "GET", "/api/v1/cost", None, "cost.json"),
    ("channels", "GET", "/api/v1/channels", None, "channels.json"),
    ("config", "GET", "/api/v1/config/models", None, "config.json"),
    ("adminUsers", "GET", "/api/v1/admin/users", None, "admin_users.json"),
    ("adminTokens", "GET", "/api/v1/admin/tokens", None, "admin_tokens.json"),
    ("adminChannels", "GET", "/api/v1/admin/channels", None, "admin_channels.json"),
    (
        "auditExport",
        "POST",
        "/api/v1/audit/export",
        {"scope": "change", "change_id": "change-1"},
        "export.json",
    ),
    (
        "configPropose",
        "POST",
        "/api/v1/config/models/propose",
        {
            "before": [{"k": "编码", "v": "openai 系"}],
            "after": [{"k": "编码", "v": "openai 系"}],
            "reason": "aggregate-only change request",
        },
        "propose.json",
    ),
]


# audit & config fixtures are keyed maps (ref->lineage, section->snapshot); the
# FE mock returns fixture[key] for /audit/{ref} and /config/{section} (see
# mock.ts auditMap[decodeURIComponent(ref)] / configMap[section]). So the
# per-request oracle is that indexed entry, not the whole map.
FIXTURE_KEY = {"audit": "routing#a1b2", "config": "models"}

CONTRACT_OVERRIDES = {
    "adminTokens": {
        "tokens": [
            {
                "id": 10,
                "name": "tk-synthetic",
                "status": "enabled",
                "remain_quota": "1000",
                "unlimited_quota": False,
                "used_quota": "10",
                "group": "prod",
                "allowed_data_levels": ["L2", "L3"],
                "expired_time": "-1",
                "accessed_time": "1710000000",
            }
        ]
    },
    "adminChannels": {
        "channels": [
            {
                "id": 20,
                "name": "Synthetic Channel",
                "type": "openai",
                "status": "green",
                "weight": 80,
                "models": ["gpt-4o"],
                "group": "sensitive",
                "region": "境外·仅脱敏",
                "lane": "sensitive",
                "used_quota": "12",
            }
        ]
    },
}


def _load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _array_template(expected_list: list) -> tuple[set, set, dict, set] | None:
    """For an array of objects, return (allowed, required, example, nullable).

    allowed  = union of keys across all variant elements;
    required = keys present in EVERY variant;
    example  = a representative NON-null value per key (None if the key is null in
               every element — a frozen-null field);
    nullable = keys that appear as null in at least one element.

    This tolerates union/variant arrays (events: sec vs perf) AND nullable fields
    (e.g. console_role: string for some users, null for others) without false
    positives, while still catching unexpected keys, type drift, and a frozen-null
    field that leaked a value (0-PHI).
    """
    dict_elems = [e for e in expected_list if isinstance(e, dict)]
    if not dict_elems:
        return None
    allowed: set = set().union(*(set(e) for e in dict_elems))
    required: set = set(dict_elems[0])
    for e in dict_elems[1:]:
        required &= set(e)
    example: dict = {}
    nullable: set = set()
    for k in allowed:
        vals = [e[k] for e in dict_elems if k in e]
        if any(v is None for v in vals):
            nullable.add(k)
        example[k] = next((v for v in vals if v is not None), None)
    return allowed, required, example, nullable


def _conforms(actual: object, expected: object, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        ak, ek = set(actual), set(expected)
        errors += [f"{path}.{k}: missing in A0 response" for k in sorted(ek - ak)]
        errors += [
            f"{path}.{k}: unexpected key in A0 response (not in contract fixture)"
            for k in sorted(ak - ek)
        ]
        for k in sorted(ak & ek):
            errors += _conforms(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected array, got {type(actual).__name__}"]
        if expected and not actual:
            # anti-vacuous: a non-empty frozen fixture array must not be satisfied
            # by an empty A0 response (that would hide a serializer that drops rows).
            return [
                f"{path}: contract fixture has {len(expected)} element(s) but A0 returned an empty array"
            ]
        tmpl = _array_template(expected)
        if tmpl is None:
            if expected:
                for i, item in enumerate(actual):
                    errors += _conforms(item, expected[0], f"{path}[{i}]")
            return errors
        allowed, required, example, nullable = tmpl
        for i, item in enumerate(actual):
            if not isinstance(item, dict):
                errors.append(f"{path}[{i}]: expected object element, got {type(item).__name__}")
                continue
            ik = set(item)
            errors += [
                f"{path}[{i}].{k}: missing (required across fixture variants)"
                for k in sorted(required - ik)
            ]
            errors += [
                f"{path}[{i}].{k}: unexpected key (not in any fixture variant)"
                for k in sorted(ik - allowed)
            ]
            for k in sorted(ik & allowed):
                av, ev = item[k], example[k]
                if av is None:
                    # null OK when the fixture shows this key nullable or always-null;
                    # error only if it is a concrete value in EVERY fixture element.
                    if k not in nullable and ev is not None:
                        errors.append(
                            f"{path}[{i}].{k}: contract field is always non-null but A0 returned null"
                        )
                elif ev is None:
                    # a field that is null in EVERY fixture element must stay null (0-PHI).
                    errors.append(
                        f"{path}[{i}].{k}: contract field is always null but A0 returned {type(av).__name__}"
                    )
                else:
                    errors += _conforms(av, ev, f"{path}[{i}].{k}")
    else:
        # scalar leaf: null is EXACT — a frozen-null field (e.g. a security event's
        # payload, forced null for 0-PHI) must stay null, and a frozen scalar must
        # not silently become null. Numbers unified (int/float).
        if expected is None:
            if actual is not None:
                errors.append(
                    f"{path}: contract fixture is null but A0 returned {type(actual).__name__}"
                )
        elif actual is None:
            errors.append(f"{path}: expected {type(expected).__name__} but A0 returned null")
        elif isinstance(expected, bool):
            if not isinstance(actual, bool):
                errors.append(f"{path}: expected bool, got {type(actual).__name__}")
        elif isinstance(expected, (int, float)):
            if isinstance(actual, bool) or not isinstance(actual, (int, float)):
                errors.append(f"{path}: expected number, got {type(actual).__name__}")
        elif isinstance(expected, str) and not isinstance(actual, str):
            errors.append(f"{path}: expected string, got {type(actual).__name__}")
    return errors


@pytest.mark.parametrize(
    "key,method,path,body,fixture",
    ENDPOINTS,
    ids=[e[0] for e in ENDPOINTS],
)
def test_a0_endpoint_conforms_to_frozen_fixture(
    key, method, path, body, fixture, a0_client
) -> None:
    expected = CONTRACT_OVERRIDES.get(key) or _load_fixture(fixture)
    if key in FIXTURE_KEY:
        expected = expected[FIXTURE_KEY[key]]

    resp = a0_client.get(path) if method == "GET" else a0_client.post(path, json=body)
    assert resp.status_code == 200, f"{key}: {method} {path} -> {resp.status_code}"

    payload = resp.json()
    # 0-PHI: A0's own deep-scan guard must accept its own response.
    serializers.assert_no_phi(payload, f"conformance:{key}")

    # structural conformance against the frozen FE contract fixture
    errors = _conforms(payload, expected)
    assert not errors, (
        f"{key} ({method} {path}) diverges from frozen contract fixture {fixture}:\n  - "
        + "\n  - ".join(errors)
    )


@pytest.mark.parametrize("section", sorted(_load_fixture("config.json").keys()))
def test_a0_config_every_frozen_section_conforms(section, a0_client) -> None:
    # config.json is a 10-section frozen contract; INT-1 originally only checked
    # /config/models, so per-section drift (built/note/fields) went uncaught.
    expected = _load_fixture("config.json")[section]
    resp = a0_client.get(f"/api/v1/config/{section}")
    assert resp.status_code == 200, f"config/{section} -> {resp.status_code}"
    payload = resp.json()
    serializers.assert_no_phi(payload, f"conformance:config:{section}")
    errors = _conforms(payload, expected)
    assert not errors, (
        f"config/{section} diverges from frozen config.json[{section}]:\n  - "
        + "\n  - ".join(errors)
    )


def test_all_thirteen_contract_endpoints_are_covered() -> None:
    # Guard against silent drift: this suite must exercise every frozen endpoint.
    assert len(ENDPOINTS) == 13
    # admin_users_mgmt.json backs the sysadmin user-management view, which is
    # auth-gated (_require_sysadmin) and therefore cannot be driven by this no-auth
    # structural suite. It has dedicated, auth-aware coverage in
    # tests/test_a0_user_mgmt.py, so it is excluded here (not silently dropped).
    structural_fixtures = {p.name for p in FIXTURES.glob("*.json")} - {"admin_users_mgmt.json"}
    assert {e[4] for e in ENDPOINTS} == structural_fixtures
