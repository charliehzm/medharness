"""Live closed-loop for the A0 user-management write proxies (through the DMZ).

Drives A0 → real new-api → A0 for the staff-account lifecycle. Unlike channels/tokens,
the user list legitimately carries STAFF email (operator identity), so the 0-PHI check
here is patient-only (cn id / mobile) — but password / access_token must never appear.
Also asserts the role guards: A0 never mints a root, and role changes mirror new-api's
hierarchy. Skipped unless MEDHARNESS_LIVE_BASE is set.
"""

from __future__ import annotations

import re
import uuid

import pytest

NAME_PREFIX = "e2euser"


def _unique(tag: str) -> str:
    # new-api keeps a soft-deleted account's username reserved in the UNIQUE index, so a
    # fresh name each run avoids colliding with a prior run's (soft-deleted) test user.
    return f"{NAME_PREFIX}{tag}{uuid.uuid4().hex[:4]}"


# Patient-only PHI markers (email is allowed — it is staff identity, not patient data).
_PATIENT = (
    re.compile(r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
)


def _assert_no_patient_phi(text: str, where: str) -> None:
    for pat in _PATIENT:
        assert pat.search(text) is None, f"patient PHI-like marker in {where}"
    for secret in ("password", "access_token"):
        assert secret not in text, f"credential field '{secret}' leaked in {where}"


def _users(http, headers) -> list[dict]:
    resp = http("GET", "/api/v1/admin/users/manage_list", headers=headers)
    assert resp.status == 200, f"manage_list: {resp.status} {resp.text[:160]}"
    return resp.json().get("users", [])


def _find(http, headers, username: str) -> dict | None:
    return next((u for u in _users(http, headers) if u.get("username") == username), None)


def _delete_leftovers(http, headers) -> None:
    for user in _users(http, headers):
        if str(user.get("username", "")).startswith(NAME_PREFIX):
            http("POST", f"/api/v1/admin/users/{user['id']}/delete", headers=headers)


@pytest.fixture
def clean_users(http, sysadmin):
    _delete_leftovers(http, sysadmin)
    yield
    _delete_leftovers(http, sysadmin)


def test_user_crud_and_role_closed_loop(http, sysadmin, clean_users) -> None:
    username = _unique("c")
    create = http(
        "POST",
        "/api/v1/admin/users",
        {
            "username": username,
            "password": "Synthetic-1",
            "display_name": "E2E Operator",
            "role": 1,
        },
        sysadmin,
    )
    assert create.status == 200 and create.json() == {"ok": True}, (
        f"create: {create.status} {create.text[:200]}"
    )

    row = _find(http, sysadmin, username)
    assert row is not None, "created user not in manage_list"
    assert row.get("role") == "normal" and row.get("status") == "enabled"
    assert isinstance(row["id"], int), "mgmt handle must be a raw int id"
    listing = http("GET", "/api/v1/admin/users/manage_list", headers=sysadmin)
    _assert_no_patient_phi(listing.text, "users manage_list")
    uid = row["id"]

    # PROMOTE normal → admin, then DEMOTE back (hierarchy: root operator out-ranks both).
    promo = http("POST", f"/api/v1/admin/users/{uid}/role", {"action": "promote"}, sysadmin)
    assert promo.status == 200 and promo.json() == {"ok": True}, (
        f"promote: {promo.status} {promo.text[:200]}"
    )
    assert _find(http, sysadmin, username).get("role") == "admin"
    demo = http("POST", f"/api/v1/admin/users/{uid}/role", {"action": "demote"}, sysadmin)
    assert demo.status == 200 and demo.json() == {"ok": True}, (
        f"demote: {demo.status} {demo.text[:200]}"
    )
    assert _find(http, sysadmin, username).get("role") == "normal"

    # PASSWORD reset (8–20 chars) and STATUS toggle.
    pw = http("POST", f"/api/v1/admin/users/{uid}/password", {"password": "Rotated-22"}, sysadmin)
    assert pw.status == 200 and pw.json() == {"ok": True}, f"password: {pw.status} {pw.text[:200]}"
    st = http("POST", f"/api/v1/admin/users/{uid}/status", {"enabled": False}, sysadmin)
    assert st.status == 200 and st.json() == {"ok": True}, f"status: {st.status} {st.text[:200]}"
    assert _find(http, sysadmin, username).get("status") == "disabled"

    # DELETE — gone.
    rm = http("POST", f"/api/v1/admin/users/{uid}/delete", headers=sysadmin)
    assert rm.status == 200 and rm.json() == {"ok": True}, f"delete: {rm.status} {rm.text[:200]}"
    assert _find(http, sysadmin, username) is None, "user still present after delete"


def test_user_create_never_mints_root_and_validates(http, sysadmin, clean_users) -> None:
    base = {"username": _unique("g"), "password": "Synthetic-1", "role": 1}
    # A0 must never create a root (role 100), and must reject malformed input.
    for patch in (
        {"role": 100},
        {"username": "bad name!"},
        {"password": "short"},
        {"username": ""},
    ):
        resp = http("POST", "/api/v1/admin/users", {**base, **patch}, sysadmin)
        assert resp.status == 400, (
            f"patch {patch} expected 400, got {resp.status} {resp.text[:160]}"
        )
    assert _find(http, sysadmin, base["username"]) is None, (
        "no guarded user should have been created"
    )


def test_user_writes_are_sysadmin_gated(http, sysadmin, clean_users) -> None:
    body = {"username": _unique("x"), "password": "Synthetic-1", "role": 1}
    assert http("POST", "/api/v1/admin/users", body).status == 401
    assert _find(http, sysadmin, body["username"]) is None
