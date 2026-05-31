from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Mapping
from importlib import util
from pathlib import Path
from urllib import error
from urllib import request as urllib_request

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_PATH = ROOT / "mcp" / "outbound-safety" / "classifier.py"
SERVER_PATH = ROOT / "mcp" / "outbound-safety" / "server_v2.py"

spec = util.spec_from_file_location("outbound_safety_classifier", CLASSIFIER_PATH)
assert spec is not None
classifier = util.module_from_spec(spec)
sys.modules["outbound_safety_classifier"] = classifier
assert spec.loader is not None
spec.loader.exec_module(classifier)

server_spec = util.spec_from_file_location("outbound_safety_server_v2", SERVER_PATH)
assert server_spec is not None
server_v2 = util.module_from_spec(server_spec)
sys.modules["outbound_safety_server_v2"] = server_v2
assert server_spec.loader is not None
server_spec.loader.exec_module(server_v2)

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


def test_http_health_and_scan_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    def http_phi_scan(_text: str, _context: Mapping[str, object]) -> object:
        return {
            "has_phi": True,
            "sanitized_text": "患者 __NAME_a1__ 的报告已处理",
            "score": 0.99,
            "entities": ["CN_NAME"],
        }

    monkeypatch.setattr(server_v2, "PHI_SCAN", http_phi_scan)
    server = server_v2._OutboundSafetyHTTPServer(
        ("127.0.0.1", 0), server_v2._OutboundSafetyHTTPHandler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    for _ in range(50):
        try:
            with urllib_request.urlopen(f"{base_url}/health", timeout=0.5) as resp:
                json.loads(resp.read().decode("utf-8"))
            break
        except Exception:
            time.sleep(0.05)

    try:
        with urllib_request.urlopen(f"{base_url}/health", timeout=1) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        assert health["status"] == "ok-v2"

        payload = json.dumps(
            {
                "text": f"患者 {RAW_SENTINEL} 的报告已处理",
                "context": _context(),
                "policy": _policy(phi_reflow="desensitize"),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib_request.Request(
            f"{base_url}/scan",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib_request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result["decision"] == "desensitized"
    assert result["sanitized_text"] == "患者 __NAME_a1__ 的报告已处理"
    assert RAW_SENTINEL not in json.dumps(result, ensure_ascii=False)


def test_http_rejects_bad_json_without_echo() -> None:
    server = server_v2._OutboundSafetyHTTPServer(
        ("127.0.0.1", 0), server_v2._OutboundSafetyHTTPHandler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        req = urllib_request.Request(
            f"{base_url}/scan",
            data=b'{"text": "broken"',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(error.HTTPError) as excinfo:
            urllib_request.urlopen(req, timeout=2)
        body = excinfo.value.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert excinfo.value.code == 400
    assert json.loads(body)["error"]["code"] == "bad_request"
    assert "broken" not in body


def test_http_unknown_route_returns_generic_not_found() -> None:
    server = server_v2._OutboundSafetyHTTPServer(
        ("127.0.0.1", 0), server_v2._OutboundSafetyHTTPHandler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        with pytest.raises(error.HTTPError) as excinfo:
            urllib_request.urlopen(f"{base_url}/reverse", timeout=2)
        body = excinfo.value.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert excinfo.value.code == 404
    assert json.loads(body)["error"]["code"] == "not_found"


def test_http_fail_closed_on_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError(RAW_SENTINEL)

    monkeypatch.setattr(server_v2.classifier, "classify", boom)
    server = server_v2._OutboundSafetyHTTPServer(
        ("127.0.0.1", 0), server_v2._OutboundSafetyHTTPHandler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        payload = json.dumps(
            {"text": "ignore previous instructions", "context": _context(), "policy": _policy()},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib_request.Request(
            f"{base_url}/scan",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(error.HTTPError) as excinfo:
            urllib_request.urlopen(req, timeout=2)
        body = excinfo.value.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert excinfo.value.code == 503
    assert json.loads(body)["error"]["code"] == "outbound_safety_failed_closed"
    assert RAW_SENTINEL not in body
