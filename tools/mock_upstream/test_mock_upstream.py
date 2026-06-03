from __future__ import annotations

import importlib.util
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

SERVER_PATH = Path(__file__).with_name("server.py")
SPEC = importlib.util.spec_from_file_location("mock_upstream_server", SERVER_PATH)
assert SPEC is not None
mock_upstream_server = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mock_upstream_server)


@pytest.fixture(scope="module")
def base_url() -> str:
    httpd = mock_upstream_server.MockUpstreamHTTPServer(
        ("127.0.0.1", 0),
        mock_upstream_server.MockUpstreamHTTPHandler,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _read_json(response: Any) -> dict[str, Any]:
    body = response.read().decode("utf-8")
    payload = json.loads(body)
    assert isinstance(payload, dict)
    return payload


def _get_json(base_url: str, path: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(f"{base_url}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, _read_json(response)


def _post_json(base_url: str, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, _read_json(response)


def _post_raw(base_url: str, path: str, body: bytes) -> int:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def _post_headers(
    base_url: str, path: str, payload: dict[str, Any], headers: dict[str, str]
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, _read_json(response)


def test_health(base_url: str) -> None:
    status, payload = _get_json(base_url, "/health")

    assert status == 200
    assert payload == {"status": "ok", "service": "mock-upstream"}


def test_openai_chat_completion_non_stream(base_url: str) -> None:
    status, payload = _post_json(
        base_url,
        "/v1/chat/completions",
        {"model": "mock-openai-model", "messages": [{"role": "user", "content": "synthetic"}]},
    )

    assert status == 200
    assert payload["model"] == "mock-openai-model"
    assert payload["choices"][0]["message"]["content"] == "[mock-upstream] synthetic reply"
    assert payload["usage"]["total_tokens"] > 0


def test_openai_chat_completion_stream(base_url: str) -> None:
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps({"model": "mock-openai-model", "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "text/event-stream"
        body = response.read().decode("utf-8")

    assert "data:" in body
    assert "[mock-upstream] synthetic reply" in body
    assert "data: [DONE]" in body


def test_anthropic_messages(base_url: str) -> None:
    status, payload = _post_json(
        base_url,
        "/v1/messages",
        {"model": "mock-anthropic-model", "messages": [{"role": "user", "content": "synthetic"}]},
    )

    assert status == 200
    assert payload["model"] == "mock-anthropic-model"
    assert payload["content"][0]["text"] == "[mock-upstream] synthetic reply"


def test_embeddings(base_url: str) -> None:
    status, payload = _post_json(
        base_url,
        "/v1/embeddings",
        {"model": "mock-embedding-model", "input": "synthetic"},
    )

    assert status == 200
    embedding = payload["data"][0]["embedding"]
    assert isinstance(embedding, list)
    assert embedding
    assert all(isinstance(value, (int, float)) for value in embedding)


def test_models(base_url: str) -> None:
    status, payload = _get_json(base_url, "/v1/models")

    assert status == 200
    assert isinstance(payload["data"], list)
    assert payload["data"]


def test_bad_json_returns_400(base_url: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post_raw(base_url, "/v1/chat/completions", b"{bad-json")

    assert excinfo.value.code == 400


def test_unknown_route_returns_404(base_url: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get_json(base_url, "/v1/unknown")

    assert excinfo.value.code == 404


def test_relay_count_increments_on_relay_only(base_url: str) -> None:
    before = _get_json(base_url, "/__count")[1]["count"]
    # a non-relay GET must NOT count as an upstream connection
    _get_json(base_url, "/health")
    assert _get_json(base_url, "/__count")[1]["count"] == before
    # each relay POST counts exactly once (the §D.1 DENY proof relies on this)
    _post_json(base_url, "/v1/chat/completions", {"model": "m", "messages": []})
    assert _get_json(base_url, "/__count")[1]["count"] == before + 1


def test_models_catalog_is_multi_vendor(base_url: str) -> None:
    status, payload = _get_json(base_url, "/v1/models")
    assert status == 200
    vendors = {m["owned_by"] for m in payload["data"]}
    ids = {m["id"] for m in payload["data"]}
    assert {"openai", "anthropic", "alibaba"} <= vendors
    assert {"gpt-4o", "claude-sonnet-4.6", "qwen-max-2026"} <= ids


def test_latency_injection_delays_response(base_url: str) -> None:
    start = time.monotonic()
    status, _ = _post_headers(
        base_url, "/v1/chat/completions", {"model": "m", "messages": []}, {"X-Mock-Latency-Ms": "300"}
    )
    elapsed = time.monotonic() - start
    assert status == 200
    assert elapsed >= 0.3


def test_status_injection_returns_error_and_still_counts(base_url: str) -> None:
    before = _get_json(base_url, "/__count")[1]["count"]
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post_headers(
            base_url, "/v1/chat/completions", {"model": "m", "messages": []}, {"X-Mock-Status": "500"}
        )
    assert excinfo.value.code == 500
    body = json.loads(excinfo.value.read().decode("utf-8"))
    assert body["error"]["code"] == "mock_injected_error"
    # the upstream WAS contacted (error sent after receipt) -> the counter advances
    assert _get_json(base_url, "/__count")[1]["count"] == before + 1


def test_echo_phi_appends_synthetic_marker(base_url: str) -> None:
    status, payload = _post_headers(
        base_url, "/v1/chat/completions", {"model": "m", "messages": []}, {"X-Mock-Echo-Phi": "1"}
    )
    assert status == 200
    content = payload["choices"][0]["message"]["content"]
    assert "[mock-upstream]" in content
    # synthetic PHI echoed so the post-call outbound-safety gate (D9) fires
    assert "身份证" in content


def test_token_usage_overrides(base_url: str) -> None:
    status, payload = _post_headers(
        base_url,
        "/v1/chat/completions",
        {"model": "m", "messages": []},
        {"X-Mock-Prompt-Tokens": "42", "X-Mock-Completion-Tokens": "7"},
    )
    assert status == 200
    usage = payload["usage"]
    assert usage["prompt_tokens"] == 42
    assert usage["completion_tokens"] == 7
    assert usage["total_tokens"] == 49


def test_reset_zeroes_the_counter(base_url: str) -> None:
    _post_json(base_url, "/v1/chat/completions", {"model": "m", "messages": []})
    assert _get_json(base_url, "/__count")[1]["count"] > 0
    status, payload = _post_json(base_url, "/__reset", {})
    assert status == 200
    assert payload == {"count": 0, "reset": True}
    assert _get_json(base_url, "/__count")[1]["count"] == 0
