"""A0 POST /api/v1/auth/login: real password auth proxied to new-api.

The Console login form posts {username, password} here; A0 forwards to new-api's
password-login endpoint and maps the new-api role int to a Console role. These
tests stub the forwarder (_new_api_login) so no real new-api / network is touched,
and pin the security-relevant contract: bad credentials -> generic 401 (never echo
new-api's message), new-api down -> 502, 2FA -> explicit-unsupported, role mapping.
"""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"

sys.path.insert(0, str(A0_DIR))

_spec = util.spec_from_file_location("a0_api_app_authlogin", A0_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
a0 = util.module_from_spec(_spec)
sys.modules["a0_api_app_authlogin"] = a0
_spec.loader.exec_module(a0)


def _login(monkeypatch: pytest.MonkeyPatch, fake, body):
    monkeypatch.setattr(a0, "_new_api_login", fake)
    client = a0.make_test_client(a0.app)
    return client.post("/api/v1/auth/login", json=body)


def test_root_login_maps_to_sysadmin(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_u, _p):
        return {"success": True, "data": {"role": 100, "username": "root", "display_name": "Root"}}

    resp = _login(monkeypatch, fake, {"username": "root", "password": "secret123"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "role": "sysadmin", "username": "root", "display_name": "Root"}


def test_admin_role_maps_to_sysadmin(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_u, _p):
        return {"success": True, "data": {"role": 10, "username": "ops"}}

    resp = _login(monkeypatch, fake, {"username": "ops", "password": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "sysadmin"


def test_common_user_maps_to_rdlead(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_u, _p):
        return {"success": True, "data": {"role": 1, "username": "dev"}}

    resp = _login(monkeypatch, fake, {"username": "dev", "password": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "rdlead"


def test_bad_credentials_return_generic_401_no_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    leaked = "user with this username not found in db table xyz"

    def fake(_u, _p):
        return {"success": False, "message": leaked}

    resp = _login(monkeypatch, fake, {"username": "root", "password": "wrong"})
    assert resp.status_code == 401
    body = resp.json()
    assert body == {"error": {"code": "unauthorized", "msg": "用户名或密码错误"}}
    assert leaked not in str(body)


def test_new_api_unavailable_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_u, _p):
        raise a0.NewApiUnavailable("connection refused")

    resp = _login(monkeypatch, fake, {"username": "root", "password": "secret123"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_unavailable"


def test_missing_fields_return_400(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_u, _p):  # pragma: no cover - must not be reached
        raise AssertionError("forwarder must not be called on invalid input")

    resp = _login(monkeypatch, fake, {"username": "root"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_params"


def test_two_factor_account_is_explicitly_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_u, _p):
        return {"success": True, "data": {"require_2fa": True}}

    resp = _login(monkeypatch, fake, {"username": "root", "password": "secret123"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "twofa_unsupported"


def test_console_role_mapping_helper() -> None:
    assert a0._console_role_from_new_api(100) == "sysadmin"
    assert a0._console_role_from_new_api(10) == "sysadmin"
    assert a0._console_role_from_new_api(1) == "rdlead"
    assert a0._console_role_from_new_api(None) == "rdlead"
    assert a0._console_role_from_new_api("garbage") == "rdlead"
