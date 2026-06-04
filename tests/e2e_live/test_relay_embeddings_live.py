"""Layer 2 — §D.1 gate over /v1/embeddings (the `input` field, not `messages`).

The compliance gate is mounted on the whole /v1 group, so /v1/embeddings is gated
too. But an embeddings body carries its text in `input` (string OR array), and the
gate's rewriteDesensitizedBody only rewrote `messages` — so PHI in `input` reached
the upstream RAW. That is a §D.1 red-line violation on a path a real client
(ComfyUI batch embeddings) uses.

EMB1/EMB3 assert the CORRECT behaviour (upstream receives the placeholder, never
the raw id). They are xfail(strict) UNTIL the gate fix lands, so the suite first
PROVES the bug reproduces against the live stack, then the fix flips them to pass
(the markers are removed in the same change as the fix). EMB2 (clean input) is a
stable baseline that holds before and after.

Skip-gated on MEDHARNESS_LIVE_BASE + a running stack, like the rest of Layer 2.
"""

from __future__ import annotations

import uuid

RAW_ID = "110101199001011237"  # SYNTHETIC valid-checksum CN-ID -> detected as L4


def _cid(tag: str) -> str:
    return f"e2e-emb-{tag}-{uuid.uuid4().hex[:8]}"


def test_emb2_clean_input_allowed(
    relay_embeddings, inject_allowlist, mock_upstream, make_model, no_phi
):
    # Baseline: a PHI-free embeddings call passes the gate and reaches the upstream.
    cid = _cid("emb2")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay_embeddings("coder", "openai", cid, "请为这段无敏感信息的文本建立向量索引。")
    assert resp.status == 200, f"EMB2: {resp.status} {resp.text[:200]}"
    assert mock_upstream.count() == 1, "EMB2: clean embeddings call should reach the upstream"
    no_phi(resp.text, "EMB2")


def test_emb1_string_input_phi_desensitized(
    relay_embeddings, inject_allowlist, mock_upstream, make_model
):
    # §D.1 red line: the upstream must receive the desensitized placeholder, never
    # the raw identifier — even when the text is in `input` rather than `messages`.
    cid = _cid("emb1")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay_embeddings("coder", "openai", cid, f"为这段文本建索引：患者身份证 {RAW_ID}。")
    assert resp.status == 200, f"EMB1: {resp.status} {resp.text[:200]}"
    assert mock_upstream.count() == 1
    received = mock_upstream.last_prompt()
    assert RAW_ID not in received, (
        f"EMB1: RAW PHI in embeddings input reached the upstream: {received[:160]}"
    )


def test_emb3_array_input_phi_desensitized(
    relay_embeddings, inject_allowlist, mock_upstream, make_model
):
    # Array-shaped input ([str, str]) must be desensitized element-wise.
    cid = _cid("emb3")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay_embeddings("coder", "openai", cid, [f"身份证 {RAW_ID}", "就诊记录摘要"])
    assert resp.status == 200, f"EMB3: {resp.status} {resp.text[:200]}"
    assert mock_upstream.count() == 1
    received = mock_upstream.last_prompt()
    assert RAW_ID not in received, (
        f"EMB3: RAW PHI in embeddings array input reached the upstream: {received[:160]}"
    )
