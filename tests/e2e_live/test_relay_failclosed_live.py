"""Layer 2 — §D.1 fail-closed: a stalled or down MCP must DENY, never fail open.

The gate calls each MCP with a 3s timeout (complianceGateTimeout). If a pre-call MCP
hangs (docker pause) or is unreachable (docker stop), the gate MUST abort with a
generic 503 and reach the upstream ZERO times — never silently pass the request
through. phi-detect is step 1, so freezing it exercises the earliest fail-closed.

ISOLATION: these cases pause/stop a SHARED container, so they affect every relay
while in effect. They restore in `finally` + wait for health, and are run in their
OWN pytest invocation by scripts/e2e_full.sh (step 4b), never concurrently with the
rest of Layer 2. If docker container control is not permitted, the case SKIPS.

Skip-gated on MEDHARNESS_LIVE_BASE + a running stack, like the rest of Layer 2.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid

import pytest

PHI = os.environ.get("MEDHARNESS_PHI_CONTAINER", "medharness-phi-detector")

GENERIC_503 = {"error": {"code": "compliance_gate_denied", "msg": "request denied by compliance gate"}}


def _cid(tag: str) -> str:
    return f"e2e-failclosed-{tag}-{uuid.uuid4().hex[:8]}"


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)


def _wait_healthy(container: str, attempts: int = 45) -> None:
    for _ in range(attempts):
        out = _docker("inspect", "-f", "{{.State.Health.Status}}", container)
        if out.stdout.strip() == "healthy":
            return
        time.sleep(2)


def test_to1_gate_timeout_on_stalled_mcp_fails_closed(
    relay, inject_allowlist, mock_upstream, make_model, no_phi
):
    # Freeze phi-detect so the gate's call to it hangs -> 3s timeout -> fail-closed.
    # (docker pause stalls the UPSTREAM MCP, which is the gate-timeout path; an
    # injected slow UPSTREAM via X-Mock-Hang would be a different path.)
    cid = _cid("to1")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    if _docker("pause", PHI).returncode != 0:
        pytest.skip("cannot pause containers in this environment")
    try:
        resp = relay("coder", "openai", cid)
    finally:
        _docker("unpause", PHI)
        _wait_healthy(PHI)
    assert resp.status == 503, f"TO1: {resp.status} {resp.text[:200]}"
    assert resp.json() == GENERIC_503, f"TO1: non-generic body {resp.text[:200]}"
    assert mock_upstream.count() == 0, "TO1: a gate timeout must not reach the upstream"
    no_phi(resp.text, "TO1")


def test_to2_mcp_down_fails_closed(relay, inject_allowlist, mock_upstream, make_model, no_phi):
    # Stop phi-detect entirely -> the gate's HTTP call gets a transport error ->
    # fail-closed. Restart + health-wait in finally so the stack is left intact.
    cid = _cid("to2")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    if _docker("stop", PHI).returncode != 0:
        pytest.skip("cannot stop containers in this environment")
    try:
        resp = relay("coder", "openai", cid)
    finally:
        _docker("start", PHI)
        _wait_healthy(PHI)
    assert resp.status == 503, f"TO2: {resp.status} {resp.text[:200]}"
    assert resp.json() == GENERIC_503, f"TO2: non-generic body {resp.text[:200]}"
    assert mock_upstream.count() == 0, "TO2: an unreachable MCP must not reach the upstream"
    no_phi(resp.text, "TO2")
