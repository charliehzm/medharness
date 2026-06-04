"""Live E2E harness for the running local docker stack.

These tests hit the REAL nginx DMZ (TLS) of a running `docker compose` stack and
are SKIPPED unless MEDHARNESS_LIVE_BASE is set, so the normal offline suite stays
green without docker. Run against the local stack with:

    MEDHARNESS_LIVE_BASE=https://localhost:18443 \
      .venv/bin/python -m pytest tests/e2e_live -q

Optional env:
    MEDHARNESS_LIVE_USER (default: admin)
    MEDHARNESS_LIVE_PASS (default: medharness123)
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Any

import pytest

BASE = os.environ.get("MEDHARNESS_LIVE_BASE", "").rstrip("/")
LIVE_USER = os.environ.get("MEDHARNESS_LIVE_USER", "admin")
LIVE_PASS = os.environ.get("MEDHARNESS_LIVE_PASS", "medharness123")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Unambiguous PHI markers that must never appear in any DMZ/BFF response body.
_PHI_PATTERNS = [
    re.compile(r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"),  # cn id-18
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),  # cn mobile
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
]


class Resp:
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)


def _request(method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> Resp:
    url = f"{BASE}{path}"
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_CTX) as resp:
            return Resp(resp.status, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return Resp(exc.code, exc.read().decode("utf-8", "replace"))


@pytest.fixture(scope="session")
def http():
    if not BASE:
        pytest.skip("set MEDHARNESS_LIVE_BASE to run live E2E (e.g. https://localhost:18443)")
    return _request


@pytest.fixture(scope="session")
def creds() -> tuple[str, str]:
    return LIVE_USER, LIVE_PASS


@pytest.fixture(scope="session")
def sysadmin(http, creds) -> dict[str, str]:
    """Log in through the DMZ and return an Authorization header for sysadmin writes.

    The admin/* GET reads are ungated, but every write proxy (channels/tokens/users
    management) requires a valid sysadmin session Bearer — this mints one once per run.
    """
    user, password = creds
    resp = http("POST", "/api/v1/auth/login", {"username": user, "password": password})
    assert resp.status == 200, f"login failed: {resp.status} {resp.text[:160]}"
    token = resp.json().get("token")
    assert token, "login returned no session token — is A0_SESSION_SECRET set on a0-api?"
    return {"Authorization": f"Bearer {token}"}


def assert_no_phi(text: str, where: str) -> None:
    for pat in _PHI_PATTERNS:
        m = pat.search(text)
        assert m is None, f"PHI-like marker in {where}: {m.group()[:6]}…"  # type: ignore[union-attr]


# Management-list secrets that are not patient PHI but MUST still never cross the A0
# boundary: plaintext provider keys, upstream base URLs, and owner user-ids.
def assert_no_mgmt_secrets(text: str, where: str, *, extra: tuple[str, ...] = ()) -> None:
    for marker in ("sk-", "base_url", "user_id", '"key"', *extra):
        assert marker not in text, f"mgmt secret '{marker}' leaked in {where}: {text[:160]}"
