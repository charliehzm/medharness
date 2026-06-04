"""A0-minted Console session token (HMAC-SHA256 Bearer, stdlib only).

A0 owns the Console session: on login it mints a signed token the browser persists
(so a refresh keeps the user logged in) and replays as Authorization: Bearer to
authorize admin-write endpoints. These tests pin mint/verify (signature + expiry +
secret), the bearer-prefix tolerance, and that login issues a token ONLY when a
secret is configured (the tolerant design keeps the existing login suite green).
"""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"
sys.path.insert(0, str(A0_DIR))

_spec = util.spec_from_file_location("a0_api_app_session", A0_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
a0 = util.module_from_spec(_spec)
sys.modules["a0_api_app_session"] = a0
_spec.loader.exec_module(a0)

SECRET = "unit-test-session-secret-0123456789abcdef"


def test_mint_verify_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    token = a0._mint_session(42, "root", "sysadmin", 100)
    claims = a0._verify_session(token)
    assert claims is not None
    assert claims["sub"] == 42
    assert claims["usr"] == "root"
    assert claims["cr"] == "sysadmin"
    assert claims["nr"] == 100
    # the `Authorization: Bearer <token>` prefix is tolerated on verify
    assert a0._verify_session("Bearer " + token) is not None


def test_tampered_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    token = a0._mint_session(1, "u", "rdlead", 1)
    assert a0._verify_session(token[:-4] + "AAAA") is None  # signature tamper
    header, body, sig = token.split(".")
    assert a0._verify_session(f"{header}.{body}x.{sig}") is None  # payload tamper
    assert a0._verify_session("not-a-token") is None
    assert a0._verify_session("") is None


def test_wrong_secret_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    token = a0._mint_session(1, "u", "rdlead", 1)
    monkeypatch.setenv("A0_SESSION_SECRET", "a-totally-different-secret-value-000000")
    assert a0._verify_session(token) is None


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    monkeypatch.setenv("A0_SESSION_TTL_SECONDS", "-1")  # exp = iat-1 -> already expired
    token = a0._mint_session(1, "u", "rdlead", 1)
    assert a0._verify_session(token) is None


def test_no_secret_means_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A0_SESSION_SECRET", raising=False)
    with pytest.raises(Exception):  # noqa: B017 - minting without a secret must fail
        a0._mint_session(1, "u", "rdlead", 1)
    assert a0._verify_session("x.y.z") is None  # verify also fails closed


def _login(monkeypatch: pytest.MonkeyPatch, data: dict) -> dict:
    monkeypatch.setattr(a0, "_new_api_login", lambda _u, _p: {"success": True, "data": data})
    client = a0.make_test_client(a0.app)
    return client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    ).json()


def test_login_issues_token_when_secret_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A0_SESSION_SECRET", SECRET)
    body = _login(monkeypatch, {"id": 7, "role": 100, "username": "root", "display_name": "Root"})
    assert body["ok"] is True and body["role"] == "sysadmin"
    assert "token" in body
    claims = a0._verify_session(body["token"])
    assert claims is not None and claims["sub"] == 7 and claims["nr"] == 100
    # the token carries NO PHI — only id + username + role
    assert set(claims) == {"sub", "usr", "cr", "nr", "iat", "exp"}


def test_login_omits_token_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A0_SESSION_SECRET", raising=False)
    body = _login(monkeypatch, {"id": 7, "role": 1, "username": "dev"})
    assert body["ok"] is True and body["role"] == "rdlead"
    assert "token" not in body  # backward-compatible: no secret -> no token, login still works
