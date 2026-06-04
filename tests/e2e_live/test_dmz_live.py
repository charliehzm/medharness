"""Live DMZ egress-allowlist + Console-serve + login tests (ADR-18 §5).

The nginx terminator must expose ONLY: /health, the Console SPA at /, the gated
relay /v1/*, and the A0 console API /api/v1/* — and default-deny everything else
(new-api's /api/* admin surface in particular).
"""

from __future__ import annotations

from conftest import assert_no_phi


def test_health_ok(http) -> None:
    r = http("GET", "/health")
    assert r.status == 200
    assert "ok" in r.text


def test_root_serves_console_spa(http) -> None:
    r = http("GET", "/")
    assert r.status == 200
    assert "MedHarness Console" in r.text
    assert "<!doctype html>" in r.text.lower()


def test_spa_fallback_for_client_routes(http) -> None:
    # client-side routes are not real files; nginx try_files falls back to index.html
    for route in ("/traffic", "/audit", "/login"):
        r = http("GET", route)
        assert r.status == 200, route
        assert "MedHarness Console" in r.text, route


def test_a0_console_api_is_proxied(http) -> None:
    r = http("GET", "/api/v1/posture")
    assert r.status == 200
    assert_no_phi(r.text, "GET /api/v1/posture")


def test_relay_path_reaches_new_api_not_404(http) -> None:
    # no token -> new-api rejects, but the request must be PROXIED (not a DMZ 404)
    r = http("POST", "/v1/chat/completions", body={"model": "x", "messages": []})
    assert r.status != 404, f"relay path was not proxied: {r.status}"


def test_login_correct_credentials(http, creds) -> None:
    user, pw = creds
    r = http("POST", "/api/v1/auth/login", body={"username": user, "password": pw})
    assert r.status == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["role"] in ("rdlead", "sysadmin")


def test_login_wrong_password_is_generic_401_no_leak(http, creds) -> None:
    user, _ = creds
    r = http(
        "POST", "/api/v1/auth/login", body={"username": user, "password": "definitely-wrong-xyz"}
    )
    assert r.status == 401
    body = r.json()
    assert body == {"error": {"code": "unauthorized", "msg": "用户名或密码错误"}}


def test_login_missing_fields_is_400(http) -> None:
    r = http("POST", "/api/v1/auth/login", body={"username": "admin"})
    assert r.status == 400


def test_control_plane_denied_at_edge(http) -> None:
    # new-api admin / bootstrap / bare control plane must all 404 at the DMZ
    for path in (
        "/api/setup",
        "/api/route",
        "/api/audit",
        "/api/user/login",
        "/api/status",
        "/api/token/",
    ):
        r = http("GET", path)
        assert r.status == 404, f"{path} should be denied at the edge, got {r.status}"


def test_security_headers_present(http) -> None:
    # HSTS + anti-clickjacking on the TLS vhost
    import ssl
    import urllib.request

    from conftest import BASE

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # check on the SPA root (the meaningful surface); /health sets its own
    # add_header which, per nginx rules, suppresses inherited server headers.
    with urllib.request.urlopen(f"{BASE}/", timeout=15, context=ctx) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
    assert "strict-transport-security" in headers
    assert headers.get("x-frame-options", "").upper() == "DENY"
