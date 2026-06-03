"""Layer 4 — business-system simulation: real client personas through the gateway.

Stdlib personas (the gateway is OpenAI/Anthropic wire-compatible) that map to §D.1
identities via the X-MedHarness-* headers, exercised end-to-end through the nginx
DMZ. Proves a drop-in business client (Dify-RAG, ComfyUI, a compliance reviewer)
gets the correct allow/deny + 0-PHI behavior. Reuses the relay harness fixtures
(tests/conftest.py); the whole module skips unless MEDHARNESS_LIVE_BASE is set.
"""

from __future__ import annotations

import uuid


def _cid(tag: str) -> str:
    return f"sim-{tag}-{uuid.uuid4().hex[:8]}"


def test_dify_rag_agent_allowed(relay, inject_allowlist, mock_upstream, make_model, no_phi):
    # Dify-RAG agent = coder persona (openai), clean knowledge-base completion.
    cid = _cid("dify")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay("coder", "openai", cid, content="根据知识库片段，总结这段诊疗规范的三个要点。")
    assert resp.status == 200, resp.text
    assert "[mock-upstream]" in resp.text
    assert mock_upstream.count() == 1
    no_phi(resp.text, "dify-rag")


def test_comfyui_agent_allowed(relay, inject_allowlist, mock_upstream, make_model, no_phi):
    # ComfyUI prompt-generation = coder persona, also a clean completion.
    cid = _cid("comfyui")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay("coder", "openai", cid, content="为一张医学示意图生成一段中文描述提示词。")
    assert resp.status == 200, resp.text
    assert "[mock-upstream]" in resp.text
    assert mock_upstream.count() == 1
    no_phi(resp.text, "comfyui")


def test_compliance_reviewer_same_family_denied(relay, inject_allowlist, mock_upstream, make_model, no_phi):
    # A compliance reviewer must use a cross-vendor model — a same-family call denies.
    cid = _cid("rev-deny")
    inject_allowlist(cid, [make_model(roles=("coder", "reviewer"))])
    mock_upstream.reset()
    resp = relay("reviewer", "openai", cid)
    assert resp.status == 503, resp.text
    assert "[mock-upstream]" not in resp.text
    assert mock_upstream.count() == 0
    no_phi(resp.text, "reviewer-deny")


def test_compliance_reviewer_cross_vendor_allowed(relay, inject_allowlist, mock_upstream, make_model, no_phi):
    cid = _cid("rev-allow")
    inject_allowlist(cid, [make_model(roles=("coder", "reviewer"))])
    mock_upstream.reset()
    resp = relay("reviewer", "anthropic", cid)  # cross-vendor -> allowed
    assert resp.status == 200, resp.text
    assert "[mock-upstream]" in resp.text
    assert mock_upstream.count() == 1
    no_phi(resp.text, "reviewer-allow")
