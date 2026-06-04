"""A0 channel-management proxies: live new-api reads + sysadmin-gated writes."""

from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A0_DIR = ROOT / "mcp" / "a0-api"

sys.path.insert(0, str(A0_DIR))

_spec = util.spec_from_file_location("a0_api_app_channelmgmt", A0_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
a0 = util.module_from_spec(_spec)
sys.modules["a0_api_app_channelmgmt"] = a0
_spec.loader.exec_module(a0)

SECRET = "unit-test-channelmgmt-secret-0123456789abcdef"


class FakeNewApi:
    def __init__(self) -> None:
        self.channels = [
            {
                "id": 42,
                "name": "Synthetic GPT Channel",
                "type": "openai",
                "status": 1,
                "weight": 80,
                "models": "gpt-4o,claude-sonnet",
                "group": "sensitive",
                "used_quota": 123,
                "key": "sk-channel-do-not-return",
                "base_url": "https://channel.example.invalid/private",
                "user_id": 1,
            }
        ]
        self.calls: list[tuple[str, str, dict | None]] = []
        self.ok = True
        self.leak = "channel key sk-channel-do-not-return failed upstream validation"

    def __call__(self, method: str, path: str, body: dict | None = None):
        self.calls.append((method, path, body))
        if method == "GET" and path.startswith("/api/channel/?"):
            return 200, {
                "success": True,
                "data": {"items": self.channels, "total": len(self.channels)},
            }
        if self.ok:
            return 200, {"success": True}
        return 200, {"success": False, "message": self.leak}

    @property
    def writes(self) -> list[tuple[str, str, dict | None]]:
        return [
            call
            for call in self.calls
            if not (call[0] == "GET" and call[1].startswith("/api/channel/?"))
        ]


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


def test_channels_live_get_serializes_whitelist(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    resp = _client().get("/api/v1/admin/channels")
    assert resp.status_code == 200
    assert fake.calls[0] == ("GET", "/api/channel/?p=1&page_size=100", None)
    row = resp.json()["channels"][0]
    assert set(row) == {
        "id",
        "name",
        "type",
        "status",
        "weight",
        "models",
        "group",
        "region",
        "lane",
        "used_quota",
    }
    assert row["models"] == ["gpt-4o", "claude-sonnet"]
    assert row["region"] == "境外·仅脱敏"
    assert row["lane"] == "sensitive"
    payload = json.dumps(resp.json(), ensure_ascii=False)
    for forbidden in (
        "key",
        "base_url",
        "user_id",
        "sk-channel-do-not-return",
        "https://channel.example.invalid/private",
    ):
        assert forbidden not in payload


def test_channel_create_requires_sysadmin(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    body = {
        "name": "Synthetic OpenAI",
        "type": "openai",
        "key": "sk-write-only",
        "models": ["gpt-4o"],
        "group": "default",
        "weight": 50,
    }
    assert _client().post("/api/v1/admin/channels", json=body).status_code == 401
    assert _client().post("/api/v1/admin/channels", json=body, headers=_rdlead()).status_code == 403
    assert fake.writes == []


def test_channel_crud_happy_path(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    cl = _client()
    create_body = {
        "name": "Synthetic OpenAI",
        "type": "openai",
        "key": "sk-write-only",
        "base_url": "https://upstream.example.invalid/v1",
        "models": ["gpt-4o"],
        "group": "default",
        "weight": 50,
    }
    created = cl.post("/api/v1/admin/channels", json=create_body, headers=_sysadmin())
    assert created.status_code == 200 and created.json() == {"ok": True}
    # new-api AddChannel binds {mode, channel:{...}}; A0 must wrap (a flat body panics it).
    # A0 also adapts the Console's free-text type → new-api's int, and the models list →
    # new-api's comma-separated string (both are bind errors otherwise).
    assert fake.writes[-1] == (
        "POST",
        "/api/channel/",
        {
            "mode": "single",
            "channel": {
                "name": "Synthetic OpenAI",
                "type": 1,
                "key": "sk-write-only",
                "models": "gpt-4o",
                "group": "default",
                "weight": 50,
                "base_url": "https://upstream.example.invalid/v1",
            },
        },
    )
    updated = cl.post(
        "/api/v1/admin/channels/42/update",
        json={"name": "Renamed", "weight": 60, "key": "sk-rewrite-only"},
        headers=_sysadmin(),
    )
    assert updated.status_code == 200 and updated.json() == {"ok": True}
    assert fake.writes[-1] == (
        "PUT",
        "/api/channel/",
        {"id": 42, "name": "Renamed", "weight": 60, "key": "sk-rewrite-only"},
    )
    # The probe RAN (new-api reachable) → a reachable/latency verdict, not a bare ok.
    tested = cl.post("/api/v1/admin/channels/42/test", headers=_sysadmin())
    assert tested.status_code == 200 and tested.json() == {
        "ok": True,
        "reachable": True,
        "latency_ms": None,
    }
    assert fake.writes[-1] == ("GET", "/api/channel/test/42", None)
    deleted = cl.post("/api/v1/admin/channels/42/delete", headers=_sysadmin())
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    assert fake.writes[-1] == ("DELETE", "/api/channel/42", None)


def test_channel_validation_rejects_bad_input(monkeypatch) -> None:
    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    cl = _client()
    valid = {
        "name": "Synthetic OpenAI",
        "type": "openai",
        "key": "sk-write-only",
        "models": ["gpt-4o"],
        "group": "default",
        "weight": 50,
    }
    for patch in (
        {"key": ""},
        {"base_url": "file:///tmp/provider"},
        {"weight": 101},
        {"models": []},
        {"group": "bad group!"},
        {"user_id": 1},
        {"type": "no-such-provider"},
        {"type": ""},
    ):
        assert (
            cl.post(
                "/api/v1/admin/channels", json={**valid, **patch}, headers=_sysadmin()
            ).status_code
            == 400
        )
    assert cl.post("/api/v1/admin/channels/not-int/delete", headers=_sysadmin()).status_code == 400
    assert fake.writes == []


def test_channel_test_unreachable_is_verdict_not_failure(monkeypatch) -> None:
    # An unreachable upstream (success:false) is a RESULT, not an operation failure — so a
    # not-yet-configured channel (e.g. a medical template with a blank key) reads honestly
    # as reachable:false rather than "操作失败". The upstream message is never echoed.
    fake = FakeNewApi()
    fake.ok = False
    _install_fake(monkeypatch, fake)
    resp = _client().post("/api/v1/admin/channels/42/test", headers=_sysadmin())
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "reachable": False, "latency_ms": None}
    assert fake.leak not in json.dumps(resp.json(), ensure_ascii=False)


def test_channel_business_failure_is_generic(monkeypatch) -> None:
    fake = FakeNewApi()
    fake.ok = False
    _install_fake(monkeypatch, fake)
    resp = _client().post("/api/v1/admin/channels/42/delete", headers=_sysadmin())
    assert resp.status_code == 422
    body = resp.json()
    assert body == {"error": {"code": "operation_failed", "msg": "操作失败"}}
    assert fake.leak not in json.dumps(body, ensure_ascii=False)


def test_channel_upstream_unavailable_maps_502(monkeypatch) -> None:
    def boom(_method, _path, _body=None):
        raise a0.NewApiUnavailable("connection refused")

    fake = FakeNewApi()
    _install_fake(monkeypatch, fake)
    monkeypatch.setattr(a0, "_new_api_admin_request", boom)
    resp = _client().post("/api/v1/admin/channels/42/delete", headers=_sysadmin())
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_unavailable"
