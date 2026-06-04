from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib import error
from urllib import request as urllib_request

import pytest

ROOT = Path(__file__).resolve().parents[1]
PHI_DIR = ROOT / "mcp" / "phi-detector"
sys.path.insert(0, str(PHI_DIR))

server_v3 = __import__("server_v3")


SYNTHETIC_ID = "110101199001011237"
SYNTHETIC_PHONE = "13912345678"
SYNTHETIC_MRN = "AB12345678"


def setup_function(function: object) -> None:
    del function
    server_v3._RUNTIME = None


def test_empty_input_returns_empty_spans() -> None:
    result = server_v3.detect_v3("")

    assert result["spans"] == []
    assert result["stats"]["recall_estimate"] == 0.0


def test_synthetic_cn_examples_detect_expected_span_types() -> None:
    text = f"患者测试样例，身份证 {SYNTHETIC_ID}，手机 {SYNTHETIC_PHONE}，病案号 {SYNTHETIC_MRN}。"
    result = server_v3.detect_v3(text)

    entity_types = {span["entity_type"] for span in result["spans"]}
    assert {"CN_ID", "CN_PHONE", "CN_MRN"}.issubset(entity_types)


def test_response_envelope_never_contains_raw_matched_text() -> None:
    text = f"身份证 {SYNTHETIC_ID} 手机 {SYNTHETIC_PHONE} 病案号 {SYNTHETIC_MRN}"
    result = server_v3.detect_v3(text)
    payload = json.dumps(result, ensure_ascii=False)

    assert "spans" in result
    assert "stats" in result
    assert "text_sha256" in result["spans"][0]
    assert SYNTHETIC_ID not in payload
    assert SYNTHETIC_PHONE not in payload
    assert SYNTHETIC_MRN not in payload


def test_presidio_runtime_skips_forward_declared_cn_name_gracefully() -> None:
    result = server_v3.detect_v3(f"患者姓名 张小明，身份证 {SYNTHETIC_ID}")

    assert "CN_NAME" in result["_meta"]["skipped_entities"]
    assert any(span["entity_type"] == "CN_ID" for span in result["spans"])


def test_cli_health_and_stdio_detect_compatibility() -> None:
    health = subprocess.run(
        [sys.executable, str(PHI_DIR / "server_v3.py"), "health"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert json.loads(health.stdout)["status"] == "ok-v3"

    request = {"id": "t1", "method": "detect", "params": {"text": f"身份证 {SYNTHETIC_ID}"}}
    stdio = subprocess.run(
        [sys.executable, str(PHI_DIR / "server_v3.py"), "serve", "--stdio"],
        input=json.dumps(request, ensure_ascii=False) + "\n",
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    response = json.loads(stdio.stdout.splitlines()[0])
    assert response["id"] == "t1"
    assert response["result"]["spans"][0]["entity_type"] == "CN_ID"


def test_spacy_missing_falls_back_to_regex_only(monkeypatch) -> None:
    class MissingSpacy:
        @staticmethod
        def load(name: str) -> None:
            raise OSError(f"missing {name}")

        @staticmethod
        def blank(language: str) -> object:
            import spacy

            return spacy.blank(language)

    monkeypatch.setitem(sys.modules, "spacy", MissingSpacy)
    server_v3._RUNTIME = None

    result = server_v3.detect_v3(f"身份证 {SYNTHETIC_ID}")

    assert result["_meta"]["regex_only"] is True
    assert result["spans"][0]["entity_type"] == "CN_ID"


def test_1k_chars_p99_under_100ms_cpu() -> None:
    text = ("合成病历片段 " * 70)[:1000]
    server_v3.detect_v3(text)

    durations = []
    for _ in range(25):
        started = time.perf_counter()
        server_v3.detect_v3(text)
        durations.append((time.perf_counter() - started) * 1000)
    p99_ms = sorted(durations)[-1]

    assert p99_ms < 100


def test_http_health_and_scan_endpoint() -> None:
    server_v3._RUNTIME = None
    raw = f"身份证 {SYNTHETIC_ID} 手机 {SYNTHETIC_PHONE}"
    payload = json.dumps({"text": raw}, ensure_ascii=False).encode("utf-8")

    server = server_v3._PhiDetectorHTTPServer(("127.0.0.1", 0), server_v3._PhiDetectorHTTPHandler)
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
        assert health["status"] == "ok-v3"

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

    assert result["summary"]["total_hits"] >= 1
    assert "text_sha256" in result["spans"][0]
    assert SYNTHETIC_ID not in json.dumps(result, ensure_ascii=False)


def test_http_rejects_bad_json_without_echo() -> None:
    server = server_v3._PhiDetectorHTTPServer(("127.0.0.1", 0), server_v3._PhiDetectorHTTPHandler)
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


def test_http_health_only_exposes_generic_error_route() -> None:
    server = server_v3._PhiDetectorHTTPServer(("127.0.0.1", 0), server_v3._PhiDetectorHTTPHandler)
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
