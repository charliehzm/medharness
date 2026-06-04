"""Live closed-loop for the A0 token-management write proxies (through the DMZ).

Locks in the token bugs the offline mocks missed, by driving A0 → real new-api → A0:
  * new-api's UpdateToken is a full overwrite → a partial quota edit must NOT wipe
    name/group (A0 read-modify-writes);
  * the Console round-trips expired_time as the string "-1" → A0 must coerce to int
    (a string would fail new-api's int64 bind with 422);
  * a status toggle rides the status_only path;
  * remain_quota must be a number — a display string like "¥180/日" is rejected.
Skipped unless MEDHARNESS_LIVE_BASE is set.
"""

from __future__ import annotations

import pytest
from conftest import assert_no_mgmt_secrets, assert_no_phi

NAME_PREFIX = "e2e-tok-"


def _tokens(http, headers) -> list[dict]:
    resp = http("GET", "/api/v1/admin/tokens", headers=headers)
    assert resp.status == 200, f"list tokens: {resp.status} {resp.text[:160]}"
    return resp.json().get("tokens", [])


def _find(http, headers, name: str) -> dict | None:
    return next((t for t in _tokens(http, headers) if t.get("name") == name), None)


def _delete_leftovers(http, headers) -> None:
    for tok in _tokens(http, headers):
        if str(tok.get("name", "")).startswith(NAME_PREFIX):
            http("POST", f"/api/v1/admin/tokens/{tok['id']}/delete", headers=headers)


@pytest.fixture
def clean_tokens(http, sysadmin):
    _delete_leftovers(http, sysadmin)
    yield
    _delete_leftovers(http, sysadmin)


def _create(http, sysadmin, name: str) -> dict:
    resp = http(
        "POST",
        "/api/v1/admin/tokens",
        {"name": name, "group": "default", "allowed_data_levels": ["L2", "L3"], "remain_quota": 180000},
        sysadmin,
    )
    assert resp.status == 200 and resp.json() == {"ok": True}, f"create: {resp.status} {resp.text[:200]}"
    row = _find(http, sysadmin, name)
    assert row is not None, "created token not present in mgmt list"
    return row


def test_token_crud_closed_loop(http, sysadmin, clean_tokens) -> None:
    name = f"{NAME_PREFIX}crud"
    row = _create(http, sysadmin, name)
    tid = row["id"]
    assert isinstance(tid, int), "mgmt handle must be a raw int id (not id_hash)"

    # 0-PHI / no plaintext secret crosses A0.
    listing = http("GET", "/api/v1/admin/tokens", headers=sysadmin)
    assert_no_mgmt_secrets(listing.text, "tokens mgmt list")
    assert_no_phi(listing.text, "tokens mgmt list")

    # QUOTA EDIT — the body is exactly what the Console sends, INCLUDING expired_time as
    # the string "-1". A0 must (a) coerce it to int and (b) carry name/group forward.
    upd = http(
        "POST",
        f"/api/v1/admin/tokens/{tid}/update",
        {"remain_quota": 220000, "unlimited_quota": False, "expired_time": "-1"},
        sysadmin,
    )
    assert upd.status == 200 and upd.json() == {"ok": True}, f"quota update: {upd.status} {upd.text[:200]}"
    after = _find(http, sysadmin, name)
    assert after is not None, "quota edit WIPED the name (read-modify-write regression!)"
    assert str(after.get("remain_quota")) == "220000", f"quota not reflected: {after}"
    assert after.get("group") == "default", "quota edit wiped the group"
    assert after.get("allowed_data_levels") == ["L2", "L3"], "data levels not preserved"

    # STATUS TOGGLE — status_only path, must not wipe anything else.
    dis = http("POST", f"/api/v1/admin/tokens/{tid}/update", {"status": "disabled"}, sysadmin)
    assert dis.status == 200 and dis.json() == {"ok": True}, f"disable: {dis.status} {dis.text[:200]}"
    after = _find(http, sysadmin, name)
    assert after is not None and after.get("status") == "disabled", f"status not reflected: {after}"
    assert str(after.get("remain_quota")) == "220000", "status toggle wiped the quota"
    http("POST", f"/api/v1/admin/tokens/{tid}/update", {"status": "enabled"}, sysadmin)

    # DELETE — gone.
    rm = http("POST", f"/api/v1/admin/tokens/{tid}/delete", headers=sysadmin)
    assert rm.status == 200 and rm.json() == {"ok": True}, f"delete: {rm.status} {rm.text[:200]}"
    assert _find(http, sysadmin, name) is None, "token still present after delete"


def test_token_quota_must_be_numeric(http, sysadmin, clean_tokens) -> None:
    name = f"{NAME_PREFIX}quota"
    tid = _create(http, sysadmin, name)["id"]
    # A display string is rejected (the original live bug was the Console sending "¥180/日").
    bad = http("POST", f"/api/v1/admin/tokens/{tid}/update", {"remain_quota": "¥180/日"}, sysadmin)
    assert bad.status == 400, f"display-string quota must be 400, got {bad.status} {bad.text[:160]}"
    # A numeric edit succeeds and the name survives.
    ok = http("POST", f"/api/v1/admin/tokens/{tid}/update", {"remain_quota": 200000}, sysadmin)
    assert ok.status == 200 and ok.json() == {"ok": True}
    after = _find(http, sysadmin, name)
    assert after is not None and str(after.get("remain_quota")) == "200000"


def test_token_writes_are_sysadmin_gated(http, sysadmin, clean_tokens) -> None:
    body = {"name": f"{NAME_PREFIX}gated", "group": "default", "allowed_data_levels": ["L2"], "remain_quota": 1000}
    assert http("POST", "/api/v1/admin/tokens", body).status == 401
    assert _find(http, sysadmin, body["name"]) is None
