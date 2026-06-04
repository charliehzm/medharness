"""Live closed-loop for the A0 channel-management write proxies (through the DMZ).

This is the layer that would have caught the channel bugs the offline mocks missed:
new-api's AddChannel panics on a flat body (A0 must wrap `{mode, channel}`), its
`type` is an int (A0 maps the Console's provider name), and its `models` is a comma
string (A0 flattens the list). Each test drives A0 → real new-api → A0 and cleans up
after itself. Skipped unless MEDHARNESS_LIVE_BASE is set.
"""

from __future__ import annotations

import pytest
from conftest import assert_no_mgmt_secrets, assert_no_phi

NAME_PREFIX = "e2e-chan-"


def _channels(http, headers) -> list[dict]:
    resp = http("GET", "/api/v1/admin/channels", headers=headers)
    assert resp.status == 200, f"list channels: {resp.status} {resp.text[:160]}"
    return resp.json().get("channels", [])


def _find(http, headers, name: str) -> dict | None:
    return next((c for c in _channels(http, headers) if c.get("name") == name), None)


def _delete_leftovers(http, headers) -> None:
    for chan in _channels(http, headers):
        if str(chan.get("name", "")).startswith(NAME_PREFIX):
            http("POST", f"/api/v1/admin/channels/{chan['id']}/delete", headers=headers)


@pytest.fixture
def clean_channels(http, sysadmin):
    _delete_leftovers(http, sysadmin)
    yield
    _delete_leftovers(http, sysadmin)


def test_channel_crud_closed_loop(http, sysadmin, clean_channels) -> None:
    name = f"{NAME_PREFIX}crud"
    # CREATE — provider name + models list + a plaintext key. A flat body would panic
    # new-api (nil-deref); a string type / list models would fail its bind. A0 adapts all.
    create = http(
        "POST",
        "/api/v1/admin/channels",
        {
            "name": name,
            "type": "openai",
            "key": "sk-e2e-channel-secret",
            "base_url": "https://upstream.example.invalid/v1",
            "models": ["gpt-4o-mini", "model-e2e"],
            "group": "default",
            "weight": 60,
        },
        sysadmin,
    )
    assert create.status == 200 and create.json() == {"ok": True}, f"create: {create.status} {create.text[:200]}"

    # READ — the row appears, models came back as a list, and NO secret crossed A0.
    row = _find(http, sysadmin, name)
    assert row is not None, "created channel not present in mgmt list"
    assert isinstance(row.get("models"), list) and "model-e2e" in row["models"]
    listing = http("GET", "/api/v1/admin/channels", headers=sysadmin)
    assert_no_mgmt_secrets(listing.text, "channels mgmt list", extra=("sk-e2e-channel-secret", "upstream.example.invalid"))
    assert_no_phi(listing.text, "channels mgmt list")
    cid = row["id"]
    assert isinstance(cid, int), "mgmt handle must be a raw int id (not id_hash)"

    # UPDATE — a partial weight edit must persist and not wipe the name.
    upd = http("POST", f"/api/v1/admin/channels/{cid}/update", {"weight": 55}, sysadmin)
    assert upd.status == 200 and upd.json() == {"ok": True}, f"update: {upd.status} {upd.text[:200]}"
    after = _find(http, sysadmin, name)
    assert after is not None and after.get("weight") == 55, f"weight not reflected: {after}"

    # TEST — the probe runs; an unreachable placeholder upstream is a verdict, not a failure.
    probe = http("POST", f"/api/v1/admin/channels/{cid}/test", headers=sysadmin)
    assert probe.status == 200, f"test: {probe.status} {probe.text[:200]}"
    verdict = probe.json()
    assert verdict.get("ok") is True and "reachable" in verdict and "latency_ms" in verdict
    assert verdict["reachable"] is False, "the example.invalid upstream must be unreachable"
    assert_no_mgmt_secrets(probe.text, "channel test verdict")

    # DELETE — the row disappears.
    rm = http("POST", f"/api/v1/admin/channels/{cid}/delete", headers=sysadmin)
    assert rm.status == 200 and rm.json() == {"ok": True}, f"delete: {rm.status} {rm.text[:200]}"
    assert _find(http, sysadmin, name) is None, "channel still present after delete"


def test_channel_writes_are_sysadmin_gated(http, sysadmin, clean_channels) -> None:
    body = {"name": f"{NAME_PREFIX}gated", "type": "openai", "key": "sk-x", "models": ["m"], "group": "default", "weight": 50}
    # No session at all → 401; the write must never reach new-api.
    assert http("POST", "/api/v1/admin/channels", body).status == 401
    assert _find(http, sysadmin, body["name"]) is None


def test_channel_bad_input_is_generic_4xx(http, sysadmin, clean_channels) -> None:
    base = {"name": f"{NAME_PREFIX}bad", "type": "openai", "key": "sk-x", "models": ["m"], "group": "default", "weight": 50}
    for patch in ({"key": ""}, {"weight": 101}, {"models": []}, {"type": "no-such-provider"}, {"base_url": "file:///etc/passwd"}):
        resp = http("POST", "/api/v1/admin/channels", {**base, **patch}, sysadmin)
        assert resp.status == 400, f"patch {patch} expected 400, got {resp.status} {resp.text[:160]}"
    assert _find(http, sysadmin, base["name"]) is None, "no bad-input channel should have been created"
