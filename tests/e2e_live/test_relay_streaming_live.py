"""Layer 2 — §D.1 post-call outbound-safety over streamed (SSE) responses.

The gate buffers the whole streamed response (bufferedComplianceWriter.Flush is a
no-op) and runs outbound-safety on it, so PHI/harmful content that stays inside a
single SSE frame is caught (ST1/ST2). But the scanner reads the framed text as one
string, so a harmful phrase SPLIT across `delta.content` chunk boundaries
("make a " | "bomb") evades the `\\bmake a bomb\\b` rule (ST3) — a streaming
outbound-evasion. ST3 asserts the CORRECT behaviour (blocked) and is xfail(strict)
until the gate reassembles delta.content before scanning; the fix flips it to pass.

Skip-gated on MEDHARNESS_LIVE_BASE + a running stack, like the rest of Layer 2.
"""

from __future__ import annotations

import uuid

GENERIC_503 = {
    "error": {"code": "compliance_gate_denied", "msg": "request denied by compliance gate"}
}


def _cid(tag: str) -> str:
    return f"e2e-stream-{tag}-{uuid.uuid4().hex[:8]}"


def test_st1_clean_stream_allowed(relay, inject_allowlist, mock_upstream, make_model, no_phi):
    # A clean streamed completion passes: 200 text/event-stream, with the chunks +
    # the [DONE] sentinel, and no PHI.
    cid = _cid("st1")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay("coder", "openai", cid, stream=True)
    assert resp.status == 200, f"ST1: {resp.status} {resp.text[:200]}"
    assert "[DONE]" in resp.text, "ST1: missing SSE [DONE] sentinel"
    assert "[mock-upstream]" in resp.text, "ST1: missing streamed upstream marker"
    assert mock_upstream.count() == 1
    no_phi(resp.text, "ST1")


def test_st2_streamed_harmful_in_single_frame_is_blocked(
    relay, inject_allowlist, echo_mock, make_model, no_phi
):
    # The harmful trigger arrives whole inside ONE SSE frame (echo-mock, no split),
    # so the outbound scan over the buffered SSE body catches it -> generic 503.
    # Proves streaming outbound-safety works for non-split content (the fix must keep
    # this true).
    cid = _cid("st2")
    inject_allowlist(cid, [make_model(model_id="echo-model", roles=("coder",))])
    echo_mock.reset()
    resp = relay("coder", "openai", cid, model="echo-model", stream=True)
    assert resp.status == 503, f"ST2: {resp.status} {resp.text[:200]}"
    assert resp.json() == GENERIC_503, f"ST2: non-generic body {resp.text[:200]}"
    assert echo_mock.count() == 1, "ST2: outbound block runs after the upstream is hit"
    no_phi(resp.text, "ST2")


def test_st3_streamed_harmful_split_across_chunks_is_blocked(
    relay, inject_allowlist, split_mock, make_model, no_phi
):
    # The harmful trigger is SPLIT across two delta.content chunks. A scan of the raw
    # SSE-framed body misses it; only a scan that reassembles delta.content catches
    # it. Correct behaviour is a generic 503 (blocked) — xfail until Fix#2 lands.
    cid = _cid("st3")
    inject_allowlist(cid, [make_model(model_id="split-model", roles=("coder",))])
    split_mock.reset()
    resp = relay("coder", "openai", cid, model="split-model", stream=True)
    assert resp.status == 503, f"ST3: {resp.status} {resp.text[:200]}"
    assert resp.json() == GENERIC_503, f"ST3: non-generic body {resp.text[:200]}"
    no_phi(resp.text, "ST3")
