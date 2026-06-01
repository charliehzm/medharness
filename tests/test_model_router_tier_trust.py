from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "model-router"))

import tier_trust  # noqa: E402,I001


SECRET = b"test-route-decision-secret"


def _decision_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision": "reroute",
        "reason": "data_level='L4' exceeds requested model_id='qwen-max' policy; reroute",
        "layer_failed": "data_level",
        "policy_version": "policy-t3.6",
        "duration_us": 123,
        "allowed_model_set": ("qwen-private",),
        "lane": "sensitive",
        "max_data_level": "L4",
        "map_id": "map-synthetic",
    }
    payload.update(overrides)
    return payload


def test_sign_and_verify_route_decision_round_trip() -> None:
    decision = _decision_payload()
    signature = tier_trust.sign_decision(decision, SECRET)

    assert tier_trust.verify_decision(decision, signature, SECRET)


def test_verify_decision_rejects_tampering() -> None:
    decision = _decision_payload()
    signature = tier_trust.sign_decision(decision, SECRET)
    forged = dict(decision)
    forged["lane"] = "normal"

    assert not tier_trust.verify_decision(forged, signature, SECRET)


def test_verify_decision_rejects_missing_signature() -> None:
    decision = _decision_payload()

    assert not tier_trust.verify_decision(decision, None, SECRET)


def test_verify_decision_rejects_missing_secret() -> None:
    decision = _decision_payload()
    signature = tier_trust.sign_decision(decision, SECRET)

    assert not tier_trust.verify_decision(decision, signature, None)
