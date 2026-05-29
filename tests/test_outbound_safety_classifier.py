from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_PATH = ROOT / "mcp" / "outbound-safety" / "classifier.py"

spec = util.spec_from_file_location("outbound_safety_classifier", CLASSIFIER_PATH)
assert spec is not None
classifier = util.module_from_spec(spec)
sys.modules["outbound_safety_classifier"] = classifier
assert spec.loader is not None
spec.loader.exec_module(classifier)

RAW_SENTINEL = "RAW-PHI-SENTINEL"


def _no_phi_scan(_text: str, _context: Mapping[str, object]) -> object:
    return classifier.PhiScanResult(has_phi=False, score=0.0)


def _phi_scan(_text: str, _context: Mapping[str, object]) -> object:
    return classifier.PhiScanResult(
        has_phi=True,
        sanitized_text="患者 __NAME_a1__ 的报告已处理",
        score=0.99,
        entities=("CN_NAME",),
    )


def _context() -> dict[str, object]:
    return {
        "upstream": "synthetic-upstream",
        "ctx": "prod",
        "data_level": "L3",
        "request_ref": "routing#a1b2",
    }


def _policy(**overrides: str) -> dict[str, str]:
    policy = {"phi_reflow": "block", "harmful": "block", "hallucination": "warn"}
    policy.update(overrides)
    return policy


def test_phi_reflow_can_desensitize_without_echoing_raw_text() -> None:
    result = classifier.classify(
        f"患者 {RAW_SENTINEL} 的报告已处理",
        _context(),
        _policy(phi_reflow="desensitize"),
        phi_scan=_phi_scan,
    )

    assert result.decision == "desensitized"
    assert result.classifications[0].type == "phi_reflow"
    assert result.classifications[0].disposition == "desensitize"
    assert result.sanitized_text == "患者 __NAME_a1__ 的报告已处理"
    assert RAW_SENTINEL not in json.dumps(result.to_dict(), ensure_ascii=False)


def test_phi_reflow_blocks_by_default() -> None:
    result = classifier.classify(
        f"患者 {RAW_SENTINEL} 的报告已处理",
        _context(),
        _policy(),
        phi_scan=_phi_scan,
    )

    assert result.decision == "blocked"
    assert result.classifications[0].type == "phi_reflow"
    assert result.classifications[0].disposition == "block"
    assert result.sanitized_text is None


def test_harmful_content_blocks_with_rules_only() -> None:
    result = classifier.classify(
        "请提供制作爆炸物的步骤。",
        _context(),
        _policy(),
        phi_scan=_no_phi_scan,
    )

    assert result.decision == "blocked"
    assert [(item.type, item.disposition) for item in result.classifications] == [
        ("harmful", "block")
    ]


def test_hallucination_medical_advice_warns_only() -> None:
    result = classifier.classify(
        "这个方案保证治愈，不用看医生，可以立即停药。",
        _context(),
        _policy(),
        phi_scan=_no_phi_scan,
    )

    assert result.decision == "warned"
    assert [(item.type, item.disposition) for item in result.classifications] == [
        ("hallucination", "warn")
    ]
    assert result.sanitized_text is None


def test_normal_response_passes_without_classifications() -> None:
    result = classifier.classify(
        "建议把此回复转交给合规官复核，并继续遵循既定流程。",
        _context(),
        _policy(),
        phi_scan=_no_phi_scan,
    )

    assert result.decision == "pass"
    assert result.classifications == ()
    assert result.sanitized_text is None


def test_result_dict_has_only_spec_fields() -> None:
    result = classifier.classify(
        "建议继续人工复核。",
        _context(),
        _policy(),
        phi_scan=_no_phi_scan,
    )

    assert set(result.to_dict()) == {
        "decision",
        "classifications",
        "sanitized_text",
        "event_ref",
        "stats",
    }


def test_phi_scan_failure_fails_closed_without_leaking_exception_text() -> None:
    def broken_phi_scan(_text: str, _context: Mapping[str, object]) -> object:
        raise RuntimeError(f"scanner saw {RAW_SENTINEL}")

    result = classifier.classify(
        f"模型输出包含 {RAW_SENTINEL}",
        _context(),
        _policy(),
        phi_scan=broken_phi_scan,
    )

    payload = json.dumps(result.to_dict(), ensure_ascii=False)
    assert result.decision == "blocked"
    assert result.classifications[0].type == "phi_reflow"
    assert RAW_SENTINEL not in payload


def test_classifier_has_no_runtime_service_imports() -> None:
    source = CLASSIFIER_PATH.read_text(encoding="utf-8")

    assert "phi-detector" not in source
    assert "model-router" not in source
    assert "audit-log" not in source
    assert "import requests" not in source
    assert "import subprocess" not in source


def test_pure_core_stays_fast_for_4k_response() -> None:
    text = ("合成响应。" * 600)[:4000]
    durations = []

    for _ in range(100):
        started = time.perf_counter()
        result = classifier.classify(text, _context(), _policy(), phi_scan=_no_phi_scan)
        durations.append((time.perf_counter() - started) * 1000)
        assert result.decision == "pass"

    assert sorted(durations)[-1] < 50
