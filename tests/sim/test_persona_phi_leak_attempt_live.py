"""Layer 4 — production-system safety: a careless client cannot leak PHI upstream.

The highest-value black-box guarantee: a business client that pastes raw PHI into
an ordinary prompt is NOT blocked (the §D.1 spine desensitizes rather than denies),
but the upstream model must receive a DESENSITIZED prompt — the raw identifier must
never egress. Verified end-to-end through the running stack.
"""

from __future__ import annotations

import uuid

SYNTHETIC_ID = "110101199001011237"  # valid-checksum synthetic CN-ID (never a real person)


def test_careless_client_phi_is_desensitized_not_leaked(
    relay, inject_allowlist, mock_upstream, make_model, no_phi
):
    cid = f"sim-phi-leak-{uuid.uuid4().hex[:8]}"
    inject_allowlist(cid, [make_model(roles=("coder",))])
    mock_upstream.reset()

    resp = relay(
        "coder", "openai", cid,
        content=f"帮我看看这位患者身份证 {SYNTHETIC_ID} 的既往就诊记录并总结。",
    )

    # desensitize-and-allow (not block): the call succeeds...
    assert resp.status == 200, resp.text
    assert "[mock-upstream]" in resp.text
    assert mock_upstream.count() == 1
    no_phi(resp.text, "phi-leak-response")

    # ...but the upstream must NEVER have seen the raw identifier.
    received = mock_upstream.last_prompt()
    assert SYNTHETIC_ID not in received, f"RAW PHI leaked to the upstream: {received[:200]}"
