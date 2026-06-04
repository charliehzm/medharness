"""A0 user-management write proxies: sysadmin-gated, replayed to new-api.

The Console user-management screen drives these POST-shaped endpoints; A0 verifies
the operator's signed session (sysadmin only), validates input locally (it NEVER
mints a root user), enforces the new-api role hierarchy on privileged actions, and
replays the mutation to new-api under a server-held admin token. These tests stub
the new-api admin forwarder (`_new_api_admin_request`) + headers helper so no real
new-api / network / token is touched, and pin the security contract:

  * the exact new-api call each endpoint builds (method / path / body),
  * sysadmin-only authorization (no session -> 401, rdlead -> 403, sysadmin -> ok),
  * the role-hierarchy pre-check (cannot demote/delete a peer-or-superior),
  * generic-error discipline (a new-api business failure never leaks its message),
  * the management serializer (staff email/display_name surface; an injected
    patient identifier is still rejected by assert_no_patient_phi).
"""

from __future__ import annotations

import json
import re
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"

sys.path.insert(0, str(A0_DIR))

_spec = util.spec_from_file_location("a0_api_app_usermgmt", A0_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
a0 = util.module_from_spec(_spec)
sys.modules["a0_api_app_usermgmt"] = a0
_spec.loader.exec_module(a0)

import serializers  # noqa: E402,I001

SECRET = "unit-test-usermgmt-secret-0123456789abcdef"
CN_ID = "110101199001011237"  # a patient identifier that must NEVER surface


# --- a capturing fake new-api admin client ------------------------------------
class FakeNewApi:
    """Router stub for ``_new_api_admin_request``; records every write call.

    GET /api/user/ returns a configurable user list (so the role-hierarchy lookup
    resolves); writes are captured and answered with a configurable outcome.
    """

    def __init__(self, users: list[dict] | None = None) -> None:
        self.users = users if users is not None else [{"id": 7, "role": 1}]
        self.calls: list[tuple[str, str, dict | None]] = []
        self.ok = True
        self.leak = "user 7 not found in db table users; sql: select * from users"

    def __call__(self, method: str, path: str, body: dict | None = None):
        self.calls.append((method, path, body))
        if method == "GET" and "?" not in path and re.fullmatch(r"/api/user/\d+", path):
            # single-user fetch used by the read-modify-write password/update path
            uid = int(path.rsplit("/", 1)[-1])
            match = next((u for u in self.users if u.get("id") == uid), None)
            return 200, ({"success": True, "data": dict(match)} if match else {"success": False})
        if method == "GET" and path.startswith("/api/user/"):
            return 200, {"success": True, "data": {"items": self.users, "total": len(self.users)}}
        if self.ok:
            return 200, {"success": True}
        # a business failure carrying new-api's own (leaky) message
        return 200, {"success": False, "message": self.leak}

    @property
    def writes(self) -> list[tuple[str, str, dict | None]]:
        return [c for c in self.calls if c[0] != "GET"]


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    monkeypatch.setenv("NEW_API_ADMIN_TOKEN", "root-admin-token-do-not-log")
    monkeypatch.setenv("NEW_API_ADMIN_USER_ID", "1")
    return monkeypatch


def _install_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeNewApi) -> None:
    monkeypatch.setattr(a0, "_new_api_admin_request", fake)
    # keep the real headers helper honest but non-None (NEW_API_ADMIN_TOKEN is set)
    assert a0._new_api_admin_headers() is not None


def _sysadmin(nr: int = 100) -> dict[str, str]:
    return {"Authorization": "Bearer " + a0._mint_session(1, "root", "sysadmin", nr)}


def _rdlead() -> dict[str, str]:
    return {"Authorization": "Bearer " + a0._mint_session(2, "dev", "rdlead", 1)}


def _client():
    return a0.make_test_client(a0.app)


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_admin_headers_bootstrap_from_root_login(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOpener:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def open(self, req, timeout=0):
            self.urls.append(req.full_url)
            if req.full_url.endswith("/api/user/login"):
                return _FakeResp({"success": True, "data": {"id": 1}})
            if req.full_url.endswith("/api/user/token"):
                return _FakeResp({"success": True, "data": {"token": "bootstrapped-token"}})
            raise AssertionError(req.full_url)

    opener = FakeOpener()
    a0._new_api_admin_cache_clear()
    monkeypatch.delenv("NEW_API_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("NEW_API_ADMIN_USER_ID", raising=False)
    monkeypatch.setenv("NEW_API_URL", "http://new-api.example.invalid")
    monkeypatch.setenv("NEW_API_ROOT_USERNAME", "admin")
    monkeypatch.setenv("NEW_API_ROOT_PASSWORD", "medharness123")
    monkeypatch.setattr(a0.request, "build_opener", lambda *_args, **_kwargs: opener)

    headers = a0._new_api_admin_headers()
    assert headers == {
        "Authorization": "bootstrapped-token",
        "New-Api-User": "1",
        "Content-Type": "application/json",
    }
    assert opener.urls == [
        "http://new-api.example.invalid/api/user/login",
        "http://new-api.example.invalid/api/user/token",
    ]


def test_admin_request_retries_once_after_401(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_auth: list[str] = []

    def fake_urlopen(req, timeout=0):
        seen_auth.append(req.headers["Authorization"])
        if len(seen_auth) == 1:
            raise a0.error.HTTPError(req.full_url, 401, "unauthorized", hdrs=None, fp=None)
        return _FakeResp({"success": True})

    a0._new_api_admin_cache_clear()
    monkeypatch.setenv("NEW_API_ADMIN_TOKEN", "stale-token")
    monkeypatch.setenv("NEW_API_ADMIN_USER_ID", "1")
    monkeypatch.setattr(a0.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(a0, "_new_api_bootstrap_admin_token", lambda: ("fresh-token", "1"))

    status, parsed = a0._new_api_admin_request("GET", "/api/user/?p=1&page_size=100")
    assert status == 200 and parsed == {"success": True}
    assert seen_auth == ["stale-token", "fresh-token"]


# --- authorization gate (representative across GET + POST) ---------------------
def test_manage_list_requires_session(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    resp = _client().get("/api/v1/admin/users/manage_list")  # no Authorization
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert fake.calls == []  # never reached new-api


def test_manage_list_rejects_rdlead(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    resp = _client().get("/api/v1/admin/users/manage_list", headers=_rdlead())
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
    assert fake.calls == []


def test_create_requires_sysadmin(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    body = {"username": "newdev", "password": "abcd1234ef", "role": 1}
    assert _client().post("/api/v1/admin/users", json=body).status_code == 401
    assert _client().post("/api/v1/admin/users", json=body, headers=_rdlead()).status_code == 403
    assert fake.writes == []  # no write attempted under either rejection


def test_admin_endpoints_502_when_bootstrap_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    monkeypatch.delenv("NEW_API_ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(
        a0,
        "_new_api_admin_headers",
        lambda: (_ for _ in ()).throw(a0.NewApiUnavailable("connection refused")),
    )
    resp = _client().get("/api/v1/admin/users/manage_list", headers=_sysadmin())
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_unavailable"


# --- manage_list: builds the list call + serializes -----------------------------
def test_manage_list_builds_list_call_and_serializes(env) -> None:
    fake = FakeNewApi()
    fake.users = [
        {
            "id": 7,
            "username": "ops",
            "display_name": "Ops Lead",
            "email": "ops@hospital.invalid",
            "role": 10,
            "status": 1,
            "group": "mgmt",
            "quota": "—",
            "used_quota": "¥12",
            "last_login_time": 1700000000,
            # source-only secrets that must never surface
            "password": "plain-do-not-return",
            "access_token": "sk-do-not-return",
        },
        # a soft-deleted account: new-api's Unscoped list still returns it, but it must
        # be filtered out of the active management view (DeletedAt is PascalCase).
        {"id": 8, "username": "ghost", "role": 1, "status": 1, "DeletedAt": "2026-01-01T00:00:00Z"},
    ]
    _install_fake(env, fake)
    resp = _client().get("/api/v1/admin/users/manage_list", headers=_sysadmin())
    assert resp.status_code == 200
    assert fake.calls[0] == ("GET", "/api/user/?p=1&page_size=100", None)
    body = resp.json()
    assert body["total"] == 1, "soft-deleted account must be filtered from the active list"
    assert [u["username"] for u in body["users"]] == ["ops"]
    row = body["users"][0]
    # staff identity surfaces (email + display_name allowed on the mgmt view)
    assert row["email"] == "ops@hospital.invalid"
    assert row["display_name"] == "Ops Lead"
    assert row["role"] == "admin" and row["status"] == "enabled"
    # secrets are whitelisted out
    assert "password" not in row and "access_token" not in row


# --- create -------------------------------------------------------------------
def test_create_builds_post_and_blocks_root_role(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    cl = _client()
    # role=100 (root) is never minted by A0
    bad = cl.post(
        "/api/v1/admin/users",
        json={"username": "x", "password": "abcd1234ef", "role": 100},
        headers=_sysadmin(),
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_params"
    assert fake.writes == []
    # a valid create builds POST /api/user/ with the whitelisted body
    ok = cl.post(
        "/api/v1/admin/users",
        json={"username": "new.dev-1", "password": "abcd1234ef", "display_name": "New", "role": 1, "group": "default"},
        headers=_sysadmin(),
    )
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    method, path, sent = fake.writes[0]
    assert method == "POST" and path == "/api/user/"
    assert sent == {
        "username": "new.dev-1",
        "password": "abcd1234ef",
        "display_name": "New",
        "role": 1,
        "group": "default",
    }


def test_create_validates_username_and_password(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    cl = _client()
    # bad username (space / too long), short password -> 400, no write
    assert cl.post("/api/v1/admin/users", json={"username": "bad name", "password": "abcd1234ef"}, headers=_sysadmin()).status_code == 400
    assert cl.post("/api/v1/admin/users", json={"username": "x" * 21, "password": "abcd1234ef"}, headers=_sysadmin()).status_code == 400
    assert cl.post("/api/v1/admin/users", json={"username": "okuser", "password": "short"}, headers=_sysadmin()).status_code == 400
    assert cl.post("/api/v1/admin/users", json={"username": "okuser", "password": "abcd1234ef", "group": "bad group!"}, headers=_sysadmin()).status_code == 400
    assert fake.writes == []


def test_create_admin_blocked_when_role_not_below_operator(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    # an admin (nr=10) may not mint another admin (role=10): not strictly lower
    resp = _client().post(
        "/api/v1/admin/users",
        json={"username": "peer", "password": "abcd1234ef", "role": 10},
        headers=_sysadmin(nr=10),
    )
    assert resp.status_code == 403
    assert fake.writes == []


# --- update -------------------------------------------------------------------
def test_update_injects_id_and_builds_put(env) -> None:
    # Read-modify-write: new-api's UpdateUser is a full overwrite (a missing username
    # trips its UNIQUE index), so A0 carries the current identity and overlays the edit.
    fake = FakeNewApi(
        users=[{"id": 42, "username": "dev42", "display_name": "Old", "role": 1, "group": "old", "email": ""}]
    )
    _install_fake(env, fake)
    resp = _client().post(
        "/api/v1/admin/users/42/update",
        json={"display_name": "Renamed", "group": "default"},
        headers=_sysadmin(),
    )
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    method, path, sent = fake.writes[0]
    assert method == "PUT" and path == "/api/user/"
    assert sent == {
        "id": 42,
        "username": "dev42",
        "display_name": "Renamed",
        "role": 1,
        "group": "default",
        "email": "",
    }


def test_update_role_change_runs_hierarchy_precheck(env) -> None:
    fake = FakeNewApi(users=[{"id": 42, "role": 1}])
    _install_fake(env, fake)
    # admin (nr=10) promoting a normal user to admin (10) is refused: new role not
    # strictly below the operator.
    resp = _client().post(
        "/api/v1/admin/users/42/update",
        json={"role": 10},
        headers=_sysadmin(nr=10),
    )
    assert resp.status_code == 403
    assert fake.writes == []  # blocked before the PUT


# --- password -----------------------------------------------------------------
def test_password_builds_put_with_id_and_password(env) -> None:
    # Read-modify-write: the new password rides on the carried-forward identity so the
    # username (UNIQUE) is present and the profile is not blanked by new-api's UpdateUser.
    fake = FakeNewApi(
        users=[{"id": 9, "username": "dev9", "display_name": "Dev Nine", "role": 1, "group": "default", "email": ""}]
    )
    _install_fake(env, fake)
    resp = _client().post(
        "/api/v1/admin/users/9/password",
        json={"password": "newpass12345"},
        headers=_sysadmin(),
    )
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert fake.writes[0] == (
        "PUT",
        "/api/user/",
        {
            "id": 9,
            "username": "dev9",
            "display_name": "Dev Nine",
            "role": 1,
            "group": "default",
            "email": "",
            "password": "newpass12345",
        },
    )


def test_password_rejects_out_of_range(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    assert _client().post("/api/v1/admin/users/9/password", json={"password": "short"}, headers=_sysadmin()).status_code == 400
    assert fake.writes == []


# --- status -------------------------------------------------------------------
def test_status_enable_disable_build_manage(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    cl = _client()
    on = cl.post("/api/v1/admin/users/3/status", json={"enabled": True}, headers=_sysadmin())
    assert on.status_code == 200
    assert fake.writes[-1] == ("POST", "/api/user/manage", {"id": 3, "action": "enable"})
    off = cl.post("/api/v1/admin/users/3/status", json={"enabled": False}, headers=_sysadmin())
    assert off.status_code == 200
    assert fake.writes[-1] == ("POST", "/api/user/manage", {"id": 3, "action": "disable"})


def test_status_requires_boolean(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    assert _client().post("/api/v1/admin/users/3/status", json={"enabled": "yes"}, headers=_sysadmin()).status_code == 400
    assert _client().post("/api/v1/admin/users/3/status", json={}, headers=_sysadmin()).status_code == 400
    assert fake.writes == []


# --- role (promote / demote) --------------------------------------------------
def test_role_promote_builds_manage_after_precheck(env) -> None:
    fake = FakeNewApi(users=[{"id": 3, "role": 1}])
    _install_fake(env, fake)
    resp = _client().post("/api/v1/admin/users/3/role", json={"action": "promote"}, headers=_sysadmin(nr=100))
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert fake.writes[-1] == ("POST", "/api/user/manage", {"id": 3, "action": "promote"})


def test_role_blocks_target_at_or_above_operator(env) -> None:
    # operator nr=10 tries to demote an admin (role=10): not strictly lower -> blocked
    fake = FakeNewApi(users=[{"id": 5, "role": 10}])
    _install_fake(env, fake)
    resp = _client().post("/api/v1/admin/users/5/role", json={"action": "demote"}, headers=_sysadmin(nr=10))
    assert resp.status_code == 403
    assert fake.writes == []  # never issued the manage call


def test_role_rejects_unknown_action(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    assert _client().post("/api/v1/admin/users/3/role", json={"action": "delete"}, headers=_sysadmin()).status_code == 400
    assert fake.writes == []


# --- delete -------------------------------------------------------------------
def test_delete_builds_manage_after_precheck(env) -> None:
    fake = FakeNewApi(users=[{"id": 8, "role": 1}])
    _install_fake(env, fake)
    resp = _client().post("/api/v1/admin/users/8/delete", headers=_sysadmin(nr=100))
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert fake.writes[-1] == ("POST", "/api/user/manage", {"id": 8, "action": "delete"})


def test_delete_blocks_peer_or_superior(env) -> None:
    # operator nr=10 tries to delete a root (role=100): blocked by hierarchy
    fake = FakeNewApi(users=[{"id": 1, "role": 100}])
    _install_fake(env, fake)
    resp = _client().post("/api/v1/admin/users/1/delete", headers=_sysadmin(nr=10))
    assert resp.status_code == 403
    assert fake.writes == []


# --- groups -------------------------------------------------------------------
def test_groups_requires_sysadmin_and_returns_static(env) -> None:
    fake = FakeNewApi()
    _install_fake(env, fake)
    assert _client().get("/api/v1/admin/groups").status_code == 401
    assert _client().get("/api/v1/admin/groups", headers=_rdlead()).status_code == 403
    ok = _client().get("/api/v1/admin/groups", headers=_sysadmin())
    assert ok.status_code == 200 and ok.json() == {"groups": ["default"]}


# --- generic-error discipline (no new-api message leak) -----------------------
def test_business_failure_returns_generic_4xx_no_leak(env) -> None:
    fake = FakeNewApi()
    fake.ok = False  # new-api answers success:false + a leaky message
    _install_fake(env, fake)
    resp = _client().post(
        "/api/v1/admin/users",
        json={"username": "newdev", "password": "abcd1234ef", "role": 1},
        headers=_sysadmin(),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body == {"error": {"code": "operation_failed", "msg": "操作失败"}}
    assert fake.leak not in str(body)  # new-api's own message never echoed


def test_upstream_unavailable_maps_to_502(env) -> None:
    def boom(_m, _p, _b=None):
        raise a0.NewApiUnavailable("connection refused")

    env.setattr(a0, "_new_api_admin_request", boom)
    resp = _client().post(
        "/api/v1/admin/users",
        json={"username": "newdev", "password": "abcd1234ef", "role": 1},
        headers=_sysadmin(),
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_unavailable"


# --- serializer 0-PHI: staff email passes, patient id rejected ----------------
def test_serializer_passes_staff_rows_and_rejects_patient_id() -> None:
    staff = {
        "items": [
            {
                "id": 1,
                "username": "ops",
                "display_name": "Ops Lead",
                "email": "ops@hospital.invalid",
                "role": 10,
                "status": 1,
                "group": "mgmt",
                "quota": "—",
                "used_quota": "¥12",
                "last_login_time": 1700000000,
            }
        ],
        "total": 1,
    }
    out = serializers.serialize_admin_users_mgmt(staff)
    assert out["users"][0]["email"] == "ops@hospital.invalid"
    assert out["users"][0]["display_name"] == "Ops Lead"
    # assert_no_patient_phi tolerates staff email...
    serializers.assert_no_patient_phi(out, "test:staff")

    # ...but an injected patient identifier (cn id) is still rejected.
    poisoned = {"items": [{"id": 2, "username": "x", "display_name": CN_ID, "role": 1, "status": 1}], "total": 1}
    with pytest.raises(serializers.PhiLeakError):
        serializers.serialize_admin_users_mgmt(poisoned)


def test_assert_no_patient_phi_allows_email_but_blocks_identifiers() -> None:
    # staff email alone must pass the patient-PHI guard (it fails the full guard)
    serializers.assert_no_patient_phi({"email": "staff@corp.invalid"}, "test")
    with pytest.raises(serializers.PhiLeakError):
        serializers.assert_no_phi({"email": "staff@corp.invalid"}, "test")
    # cn id / mobile / bank card are blocked by BOTH guards
    for bad in (CN_ID, "13900000000", "6222021234567890123"):
        with pytest.raises(serializers.PhiLeakError):
            serializers.assert_no_patient_phi({"x": bad}, "test")
