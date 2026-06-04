"""A0 token-management proxies: live new-api reads + sysadmin-gated writes."""

from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"

sys.path.insert(0, str(A0_DIR))

_spec = util.spec_from_file_location("a0_api_app_tokenmgmt", A0_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
a0 = util.module_from_spec(_spec)
sys.modules["a0_api_app_tokenmgmt"] = a0
_spec.loader.exec_module(a0)

SECRET = "unit-test-tokenmgmt-secret-0123456789abcdef"


class FakeNewApi:
    def __init__(self) -> None:
        self.tokens = [
            {
                "id": 77,
                "user_id": 1,
                "key": "sk-token-do-not-return",
                "name": "Synthetic App Token",
                "status": 1,
                "remain_quota": 1000,
                "unlimited_quota": False,
                "used_quota": 12,
                "group": "prod",
                "model_limits": ["gpt-4o"],
                "expired_time": -1,
                "accessed_time": 1710000000,
                "base_url": "https://token.example.invalid/private",
            }
        ]
        self.calls: list[tuple[str, str, dict | None]] = []
        self.ok = True
        self.leak = "token user_id=1 key sk-token-do-not-return violates upstream rule"

    def __call__(self, method: str, path: str, body: dict | None = None):
        self.calls.append((method, path, body))
        if method == "GET" and path.startswith("/api/token/?"):
            return 200, {"success": True, "data": {"items": self.tokens, "total": len(self.tokens)}}
        if method == "GET" and path.startswith("/api/token/"):
            # single-token fetch used by the read-modify-write update path
            tid = a0._coerce_int(path.rsplit("/", 1)[-1], -1)
            for tok in self.tokens:
                if tok["id"] == tid:
                    return 200, {"success": True, "data": dict(tok)}
            return 200, {"success": False}
        if self.ok:
            return 200, {"success": True}
        return 200, {"success": False, "message": self.leak}

    @property
    def writes(self) -> list[tuple[str, str, dict | None]]:
        # Only mutations: read-modify-write does a GET before the PUT, which is not a write.
        return [call for call in self.calls if call[0] != "GET"]


def _install_fake(monkeypatch, fake: FakeNewApi) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    monkeypatch.setenv("NEW_API_ADMIN_TOKEN", "root-admin-token-do-not-log")
    monkeypatch.setenv("NEW_API_ADMIN_USER_ID", "1")
    a0._new_api_admin_cache_clear()
    monkeypatch.setattr(a0, "_new_api_admin_request", fake)
    monkeypatch.setattr(a0, "_audit_rows", lambda limit=None: [])
    assert a0._new_api_admin_headers() is not None


def _sysadmin() -> dict[str, str]:
    return {"Authorization": "Bearer " + a0._mint_session(1, "root", "sysadmin", 100)}


def _rdlead() -> dict[str, str]:
    return {"Authorization": "Bearer " + a0._mint_session(2, "dev", "rdlead", 1)}


def _client():
    return a0.make_test_client(a0.app)


def test_tokens_live_get_serializes_whitelist(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    resp = _client().get("/api/v1/admin/tokens")
    assert resp.status_code == 200
    assert fake.calls[0] == ("GET", "/api/token/?p=1&page_size=100", None)
    row = resp.json()["tokens"][0]
    assert set(row) == {
        "id",
        "name",
        "status",
        "remain_quota",
        "unlimited_quota",
        "used_quota",
        "group",
        "allowed_data_levels",
        "expired_time",
        "accessed_time",
    }
    assert row["status"] == "enabled"
    assert row["unlimited_quota"] is False
    assert row["allowed_data_levels"] == ["L2", "L3"]
    payload = json.dumps(resp.json(), ensure_ascii=False)
    for forbidden in ("key", "user_id", "base_url", "sk-token-do-not-return", "https://token.example.invalid/private"):
        assert forbidden not in payload


def test_token_create_requires_sysadmin(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    body = {"name": "Synthetic App Token", "remain_quota": 1000, "group": "default", "allowed_data_levels": ["L2", "L3"]}
    assert _client().post("/api/v1/admin/tokens", json=body).status_code == 401
    assert _client().post("/api/v1/admin/tokens", json=body, headers=_rdlead()).status_code == 403
    assert fake.writes == []


def test_token_crud_happy_path(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    cl = _client()
    create_body = {"name": "Synthetic App Token", "remain_quota": 1000, "group": "default", "allowed_data_levels": ["L2", "L3"], "expired_time": -1}
    created = cl.post("/api/v1/admin/tokens", json=create_body, headers=_sysadmin())
    assert created.status_code == 200 and created.json() == {"ok": True}
    assert fake.writes[-1] == ("POST", "/api/token/", create_body)
    unlimited_body = {"name": "Synthetic Unlimited", "unlimited_quota": True, "group": "default", "allowed_data_levels": ["L2"]}
    unlimited = cl.post("/api/v1/admin/tokens", json=unlimited_body, headers=_sysadmin())
    assert unlimited.status_code == 200 and unlimited.json() == {"ok": True}
    assert fake.writes[-1] == ("POST", "/api/token/", unlimited_body)
    # A partial quota edit is a READ-MODIFY-WRITE: new-api's UpdateToken overwrites every
    # native field, so A0 must carry name/group/expiry forward and change only the quota.
    # Asserting the full merged body is the regression guard against the field-wipe bug.
    updated = cl.post("/api/v1/admin/tokens/77/update", json={"remain_quota": 2000, "allowed_data_levels": ["L2", "L3"]}, headers=_sysadmin())
    assert updated.status_code == 200 and updated.json() == {"ok": True}
    assert fake.writes[-1] == (
        "PUT",
        "/api/token/",
        {
            "id": 77,
            "name": "Synthetic App Token",
            "group": "prod",
            "expired_time": -1,
            "remain_quota": 2000,
            "unlimited_quota": False,
            "model_limits": ["gpt-4o"],
        },
    )
    # A status toggle rides new-api's status_only path (int status), never wiping fields.
    toggled = cl.post("/api/v1/admin/tokens/77/update", json={"status": "disabled"}, headers=_sysadmin())
    assert toggled.status_code == 200 and toggled.json() == {"ok": True}
    assert fake.writes[-1] == ("PUT", "/api/token/?status_only=1", {"id": 77, "status": 2})
    deleted = cl.post("/api/v1/admin/tokens/77/delete", headers=_sysadmin())
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    assert fake.writes[-1] == ("DELETE", "/api/token/77", None)


def test_token_validation_rejects_bad_input(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    cl = _client()
    valid = {"name": "Synthetic App Token", "remain_quota": 1000, "group": "default", "allowed_data_levels": ["L2", "L3"]}
    for patch in ({"remain_quota": None, "unlimited_quota": False}, {"allowed_data_levels": ["L9"]}, {"group": "bad group!"}, {"key": "sk-should-not-pass"}, {"user_id": 1}):
        body = {**valid, **patch}
        if patch.get("remain_quota") is None:
            body.pop("remain_quota", None)
        assert cl.post("/api/v1/admin/tokens", json=body, headers=_sysadmin()).status_code == 400
    assert cl.post("/api/v1/admin/tokens/abc/delete", headers=_sysadmin()).status_code == 400
    assert cl.post("/api/v1/admin/tokens/77/update", json={"key": "sk-no"}, headers=_sysadmin()).status_code == 400
    assert fake.writes == []


def test_token_business_failure_is_generic(monkeypatch) -> None:
    fake = FakeNewApi()
    fake.ok = False
    _install_fake(monkeypatch, fake)
    resp = _client().post("/api/v1/admin/tokens/77/delete", headers=_sysadmin())
    assert resp.status_code == 422
    body = resp.json()
    assert body == {"error": {"code": "operation_failed", "msg": "操作失败"}}
    assert fake.leak not in json.dumps(body, ensure_ascii=False)


def test_token_upstream_unavailable_maps_502(monkeypatch) -> None:
    def boom(_method, _path, _body=None):
        raise a0.NewApiUnavailable("connection refused")

    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    monkeypatch.setattr(a0, "_new_api_admin_request", boom)
    resp = _client().post("/api/v1/admin/tokens/77/delete", headers=_sysadmin())
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_unavailable"
