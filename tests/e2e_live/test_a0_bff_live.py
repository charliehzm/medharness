"""Live A0 Console BFF tests against the running stack (through the nginx DMZ).

Every endpoint must return its contract status and leak no PHI. Requires the
ClickHouse _audit_log table to be seeded (scripts/dev_seed_audit.py) so the
read endpoints return 200 rather than fail-closed 503.
"""

from __future__ import annotations

import urllib.parse

import pytest
from conftest import assert_no_phi

CONFIG_SECTIONS = (
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
)

READ_ENDPOINTS = ("posture", "traffic", "events", "cost", "channels", "upstreams")
ADMIN_ENDPOINTS = ("admin/users", "admin/tokens", "admin/channels")


@pytest.fixture(scope="session")
def real_ref(http) -> str:
    r = http("GET", "/api/v1/events?limit=5")
    assert r.status == 200, "events must be seeded for the audit-by-ref test"
    events = r.json().get("events", [])
    assert events, "no seeded events — run scripts/dev_seed_audit.py"
    return events[0]["ref"]


@pytest.mark.parametrize("ep", READ_ENDPOINTS)
def test_read_endpoint_200_and_no_phi(http, ep) -> None:
    r = http("GET", f"/api/v1/{ep}")
    assert r.status == 200, f"{ep}: {r.status} {r.text[:160]}"
    assert_no_phi(r.text, f"GET /api/v1/{ep}")


@pytest.mark.parametrize("section", CONFIG_SECTIONS)
def test_config_section_200_and_no_phi(http, section) -> None:
    r = http("GET", f"/api/v1/config/{section}")
    assert r.status == 200, f"config/{section}: {r.status}"
    assert_no_phi(r.text, f"GET /api/v1/config/{section}")


def test_config_unknown_section_is_404(http) -> None:
    r = http("GET", "/api/v1/config/not-a-section")
    assert r.status == 404


@pytest.mark.parametrize("ep", ADMIN_ENDPOINTS)
def test_admin_endpoint_200_and_no_phi(http, ep) -> None:
    r = http("GET", f"/api/v1/{ep}")
    assert r.status == 200, f"{ep}: {r.status}"
    assert_no_phi(r.text, f"GET /api/v1/{ep}")


def test_audit_by_valid_ref_returns_lineage(http, real_ref) -> None:
    enc = urllib.parse.quote(real_ref)
    r = http("GET", f"/api/v1/audit/{enc}")
    assert r.status == 200, f"audit/{real_ref}: {r.status} {r.text[:160]}"
    body = r.json()
    assert body.get("ref") == real_ref
    assert "nodes" in body and "details" in body
    assert_no_phi(r.text, "GET /api/v1/audit/<ref>")


def test_audit_by_missing_ref_is_generic_404(http) -> None:
    r = http("GET", "/api/v1/audit/routing%23ffffffff")
    assert r.status == 404
    assert "error" in r.json()


def test_audit_export_writes_and_returns_200(http) -> None:
    r = http("POST", "/api/v1/audit/export", body={"scope": "all", "window": "24h"})
    assert r.status == 200, f"{r.status} {r.text[:160]}"
    assert_no_phi(r.text, "POST /api/v1/audit/export")


def test_config_propose_valid_section_200(http) -> None:
    r = http("POST", "/api/v1/config/thresholds/propose", body={"note": "e2e probe"})
    assert r.status == 200, f"{r.status} {r.text[:160]}"


def test_config_propose_unknown_section_404(http) -> None:
    r = http("POST", "/api/v1/config/not-a-section/propose", body={"note": "x"})
    assert r.status == 404
