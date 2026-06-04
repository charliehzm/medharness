"""Layer 4 (extended) — realistic business/production client personas.

Each persona is a real drop-in client workload mapped to a §D.1 identity, exercised
end-to-end through the DMZ. They assert the persona's journey: correct allow, and —
for any PHI-bearing workload — that the raw identifier is desensitized before it
reaches the upstream (the §D.1 red line). Complements the gate matrix by exercising
the SHAPES a real client sends (multi-turn RAG, batch embeddings, a dev paste).

Skip-gated on MEDHARNESS_LIVE_BASE + a running stack.
"""

from __future__ import annotations

import uuid

RAW_ID = "110101199001011237"  # SYNTHETIC valid-checksum CN-ID


def _cid(tag: str) -> str:
    return f"sim-persona-{tag}-{uuid.uuid4().hex[:8]}"


def test_claude_code_accidental_phi_paste_is_desensitized(
    relay, inject_allowlist, mock_upstream, make_model, no_phi
):
    # Dev-period Claude Code: an engineer pastes a debug snippet that accidentally
    # contains a patient identifier. It must be desensitized, not leaked upstream.
    cid = _cid("claude-code")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    prompt = f"这个查询为什么报错？SELECT * FROM patients WHERE id_card='{RAW_ID}';"
    resp = relay("coder", "openai", cid, content=prompt)
    assert resp.status == 200, resp.text
    assert mock_upstream.count() == 1
    assert RAW_ID not in mock_upstream.last_prompt(), "accidental PHI paste reached the upstream"
    no_phi(resp.text, "claude-code")


def test_dify_rag_multi_note_conversation_is_desensitized(
    relay, inject_allowlist, mock_upstream, make_model, no_phi
):
    # Prod Dify-RAG: a multi-turn conversation whose retrieved notes carry PHI. Every
    # message must be desensitized before the prompt egresses.
    cid = _cid("dify-rag")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    msgs = [
        {"role": "system", "content": "你是诊疗助手，只输出脱敏后的占位符。"},
        {"role": "user", "content": f"检索到的病历：患者身份证 {RAW_ID}，主诉发热三天。"},
        {"role": "user", "content": "请根据上面的病历总结随访建议。"},
    ]
    resp = relay("coder", "openai", cid, messages=msgs)
    assert resp.status == 200, resp.text
    assert mock_upstream.count() == 1
    assert RAW_ID not in mock_upstream.last_prompt(), "RAG note PHI reached the upstream"
    no_phi(resp.text, "dify-rag")


def test_comfyui_batch_embeddings_is_desensitized(
    relay_embeddings, inject_allowlist, mock_upstream, make_model, no_phi
):
    # Prod ComfyUI batch: an array of discharge-summary fragments embedded at once,
    # one of which carries PHI. The array must be desensitized element-wise.
    cid = _cid("comfyui")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    batch = [f"出院小结：身份证 {RAW_ID}", "随访计划：两周后复诊", "用药：每日一次"]
    resp = relay_embeddings("coder", "openai", cid, batch)
    assert resp.status == 200, resp.text
    assert mock_upstream.count() == 1
    assert RAW_ID not in mock_upstream.last_prompt(), "batch embeddings PHI reached the upstream"
    no_phi(resp.text, "comfyui")


def test_custom_billing_app_clean_workload_allowed(
    relay, inject_allowlist, mock_upstream, make_model, no_phi
):
    # A custom in-house billing app sending a PHI-free aggregate query — clean allow.
    cid = _cid("billing")
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()
    resp = relay("coder", "openai", cid, content="按月汇总各科室的接口调用量与成本，给出节流建议。")
    assert resp.status == 200, resp.text
    assert "[mock-upstream]" in resp.text
    assert mock_upstream.count() == 1
    no_phi(resp.text, "billing")
