from __future__ import annotations

import json
import queue
import sys
import threading
import time
from collections.abc import Mapping
from importlib import util
from pathlib import Path
from urllib import request as urllib_request

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTBOUND_DIR = ROOT / "mcp" / "outbound-safety"
ASYNC_CATCH_PATH = OUTBOUND_DIR / "async_catch.py"
SERVER_PATH = OUTBOUND_DIR / "server_v2.py"


def _load_module(module_name: str, path: Path) -> object:
    spec = util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


async_catch = _load_module("outbound_safety_async_catch_test", ASYNC_CATCH_PATH)
server_v2 = _load_module("outbound_safety_server_v2_async_test", SERVER_PATH)

RAW_SENTINEL = "RAW-PHI-SENTINEL"


def _no_phi_scan(_text: str, _context: Mapping[str, object]) -> object:
    return {"has_phi": False, "score": 0.0}


def _context() -> dict[str, object]:
    return {
        "upstream": "synthetic-upstream",
        "ctx": "prod",
        "data_level": "L3",
        "request_ref": "routing#async",
    }


def _policy(**overrides: str) -> dict[str, str]:
    policy = {"phi_reflow": "block", "harmful": "block", "hallucination": "warn"}
    policy.update(overrides)
    return policy


def _post_scan(base_url: str, text: str, timeout: float = 2.0) -> dict[str, object]:
    payload = json.dumps(
        {"text": text, "context": _context(), "policy": _policy()},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib_request.Request(
        f"{base_url}/scan",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _start_server() -> tuple[object, threading.Thread, str]:
    server = server_v2._OutboundSafetyHTTPServer(
        ("127.0.0.1", 0), server_v2._OutboundSafetyHTTPHandler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


def _stop_server(server: object, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _reset_async_state(maxsize: int = 256) -> None:
    server_v2._ASYNC_CATCH_QUEUE = queue.Queue(maxsize=maxsize)
    server_v2._ASYNC_CATCH_WORKER = None
    server_v2._ASYNC_CATCH_COUNTERS = {
        "processed": 0,
        "caught": 0,
        "dropped": 0,
    }
    server_v2._ASYNC_CATCH_RING.clear()
    server_v2.ASYNC_SINK = server_v2._default_async_sink


@pytest.fixture(autouse=True)
def _clean_server_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_async_state()
    monkeypatch.setattr(server_v2, "PHI_SCAN", _no_phi_scan)


def test_cn_name_inline_miss_is_caught_hash_only() -> None:
    raw_name = "欧阳静"
    findings = async_catch.scan_missed(f"主诉头痛三天，患者{raw_name}今日复诊。")

    cn_findings = [item for item in findings if item.entity_type == "CN_NAME"]
    assert cn_findings
    event = cn_findings[0].to_event_dict()
    assert event["value_sha256"]
    assert raw_name not in json.dumps(event, ensure_ascii=False)
    assert set(event) == {"entity_type", "score", "start", "end", "value_sha256"}


def test_mrn_context_caught_and_ordinary_prose_not_flagged() -> None:
    findings = async_catch.scan_missed("患者已完成复核，病案号 1234567。")

    assert any(item.entity_type == "MRN" for item in findings)
    assert async_catch.scan_missed("建议继续观察 1234567 这个一般数字示例。") == ()


def test_server_scan_returns_inline_result_and_emits_async_finding() -> None:
    events: list[dict[str, object]] = []
    server_v2.ASYNC_SINK = events.append
    server, thread, base_url = _start_server()

    try:
        result = _post_scan(base_url, f"主诉头痛，患者欧阳静今日复诊。备注{RAW_SENTINEL}。")
        for _ in range(50):
            if events:
                break
            time.sleep(0.05)
    finally:
        _stop_server(server, thread)

    assert result["decision"] == "pass"
    assert set(result) == {
        "decision",
        "classifications",
        "sanitized_text",
        "event_ref",
        "stats",
    }
    assert events
    assert events[0]["entity_type"] == "CN_NAME"
    assert RAW_SENTINEL not in json.dumps(events, ensure_ascii=False)


def test_full_queue_does_not_block_scan_and_increments_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_async_state(maxsize=1)
    server_v2._ASYNC_CATCH_QUEUE.put_nowait(("already queued", False))
    monkeypatch.setattr(server_v2, "_ensure_async_catch_worker", lambda: None)
    server, thread, base_url = _start_server()

    try:
        started = time.perf_counter()
        result = _post_scan(base_url, "主诉稳定，患者欧阳静今日复诊。")
        duration_ms = (time.perf_counter() - started) * 1000
    finally:
        _stop_server(server, thread)

    assert result["decision"] == "pass"
    assert duration_ms < 500
    assert server_v2.health()["async_catch"]["dropped"] == 1


def test_worker_exception_is_swallowed_and_thread_stays_alive() -> None:
    calls = 0

    def broken_sink(_event: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError(RAW_SENTINEL)

    server_v2.ASYNC_SINK = broken_sink
    server_v2._ensure_async_catch_worker()
    server_v2._ASYNC_CATCH_QUEUE.put_nowait(
        (f"主诉头痛，患者欧阳静今日复诊。备注{RAW_SENTINEL}。", False)
    )

    for _ in range(50):
        if calls:
            break
        time.sleep(0.05)

    assert calls == 1
    assert server_v2._ASYNC_CATCH_WORKER is not None
    assert server_v2._ASYNC_CATCH_WORKER.is_alive()
    assert server_v2.health()["async_catch"]["processed"] >= 1
    assert RAW_SENTINEL not in json.dumps(server_v2.health(), ensure_ascii=False)
