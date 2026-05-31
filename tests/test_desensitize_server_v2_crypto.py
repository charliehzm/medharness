from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib import error
from urllib import request as urllib_request

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESENSITIZE_DIR = ROOT / "mcp" / "desensitize"
sys.path.insert(0, str(DESENSITIZE_DIR))

import server_v2  # noqa: E402
from key_provider.file_provider import FileKeyProvider  # noqa: E402

TOKEN = "synthetic-token"


def _span(text: str, raw: str, entity_type: str = "CN_ID") -> dict[str, object]:
    start = text.index(raw)
    end = start + len(raw)
    return {
        "start": start,
        "end": end,
        "entity_type": entity_type,
        "score": 0.99,
        "text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def _request(text: str, raw: str, map_id: str = "map-synthetic") -> dict[str, object]:
    return {
        "text": text,
        "phi_spans": [_span(text, raw)],
        "context": {"change_id": "change-t2", "map_id": map_id, "key_id": "active"},
    }


def _reverse_request(result: dict[str, object]) -> dict[str, object]:
    return {
        "map_ref": result["map_ref"],
        "metadata": result["metadata"],
        "context": {"change_id": "change-t2", "map_id": "map-synthetic", "key_id": "active"},
        "kms_token": TOKEN,
    }


def test_desensitize_reverse_roundtrip_and_no_raw_response(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    raw = "SYNTHETIC-PHI-0000000001"
    text = f"patient marker {raw} ok"

    result = server_v2.desensitize(_request(text, raw), provider)
    reverse = server_v2.reverse(_reverse_request(result), provider)
    payload = json.dumps(result, ensure_ascii=False)

    assert set(result) >= {"desensitized_text", "map_ref", "metadata"}
    assert "map_blob" not in result
    assert result["desensitized_text"] != text
    assert len(result["desensitized_text"]) == len(text)
    assert raw not in payload
    assert raw not in result["desensitized_text"]
    assert reverse["mapping"] == {next(iter(reverse["mapping"].keys())): raw}


def test_old_generation_decrypts_after_rotation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    raw = "SYNTHETIC-PHI-0000000001"
    text = f"patient marker {raw} ok"
    result = server_v2.desensitize(_request(text, raw), provider)

    provider.rotate("active")
    provider.rotate("active")
    reverse = server_v2.reverse(_reverse_request(result), provider)

    assert reverse["mapping"]
    assert list(reverse["mapping"].values()) == [raw]


def test_pruned_old_generation_returns_json_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore", max_generations=2)
    raw = "SYNTHETIC-PHI-0000000001"
    text = f"patient marker {raw} ok"
    result = server_v2.desensitize(_request(text, raw), provider)

    provider.rotate("active")
    provider.rotate("active")
    reverse = server_v2.reverse(_reverse_request(result), provider)

    assert reverse["error"]["type"] == "KeyNotFoundError"
    assert raw not in json.dumps(reverse, ensure_ascii=False)


def test_tampered_aad_sha_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    raw = "SYNTHETIC-PHI-0000000001"
    result = server_v2.desensitize(_request(f"patient marker {raw} ok", raw), provider)
    tampered = _reverse_request(result)
    tampered["metadata"] = dict(tampered["metadata"])
    tampered["metadata"]["aad_sha256"] = "0" * 64

    reverse = server_v2.reverse(tampered, provider)

    assert reverse["error"]["type"] == "KeyProviderError"
    assert "AAD metadata mismatch" in reverse["error"]["message"]


def test_placeholder_is_deterministic_and_length_preserving(tmp_path: Path) -> None:
    provider = FileKeyProvider(tmp_path / "keystore")
    raw = "SYNTHETIC-PHI-0000000001"
    text = f"patient marker {raw} ok"

    first = server_v2.desensitize(_request(text, raw), provider)
    second = server_v2.desensitize(_request(text, raw, map_id="map-synthetic-2"), provider)

    assert first["desensitized_text"] == second["desensitized_text"]
    assert len(first["desensitized_text"]) == len(text)


def test_invalid_reverse_token_denies_without_plaintext(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    raw = "SYNTHETIC-PHI-0000000001"
    result = server_v2.desensitize(_request(f"patient marker {raw} ok", raw), provider)
    request = _reverse_request(result)
    request["kms_token"] = "wrong"

    reverse = server_v2.reverse(request, provider)

    assert reverse["error"]["type"] == "PermissionError"
    assert raw not in json.dumps(reverse, ensure_ascii=False)


def test_reverse_allowed_uses_constant_time_compare(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return left == right

    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    monkeypatch.setattr(server_v2.hmac, "compare_digest", _compare_digest)

    assert server_v2._reverse_allowed({"kms_token": TOKEN, "context": {"kms_token": TOKEN}})
    assert not server_v2._reverse_allowed({"kms_token": "wrong"})
    assert calls == [(TOKEN, TOKEN), ("wrong", TOKEN)]


@contextmanager
def _running_http_server(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MEDHARNESS_KEYSTORE_ROOT", str(tmp_path / "keystore"))
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    monkeypatch.delenv("CLICKHOUSE_HTTP_PORT", raising=False)
    monkeypatch.delenv("CLICKHOUSE_DATABASE", raising=False)
    monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    server = server_v2._DesensitizeHTTPServer(("127.0.0.1", 0), server_v2._DesensitizeHTTPHandler)
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
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_health_and_encrypt_endpoint(monkeypatch, tmp_path: Path) -> None:
    raw = "SYNTHETIC-PHI-0000000001"
    text = f"patient marker {raw} ok"

    with _running_http_server(monkeypatch, tmp_path) as base_url:
        with urllib_request.urlopen(f"{base_url}/health", timeout=1) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        assert health["status"] == "ok-v2"

        payload = json.dumps(_request(text, raw), ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            f"{base_url}/encrypt",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib_request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode("utf-8"))

    assert result["desensitized_text"] != text
    assert raw not in json.dumps(result, ensure_ascii=False)
    assert set(result) >= {"desensitized_text", "map_ref", "metadata"}


def test_http_rejects_bad_json_without_echo(monkeypatch, tmp_path: Path) -> None:
    with _running_http_server(monkeypatch, tmp_path) as base_url:
        req = urllib_request.Request(
            f"{base_url}/encrypt",
            data=b'{"text": "broken"',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(error.HTTPError) as excinfo:
            urllib_request.urlopen(req, timeout=2)
        body = excinfo.value.read().decode("utf-8")

    assert excinfo.value.code == 400
    assert json.loads(body)["error"]["code"] == "bad_request"
    assert "broken" not in body
    assert "text" not in body


def test_http_unknown_route_returns_generic_not_found(monkeypatch, tmp_path: Path) -> None:
    with _running_http_server(monkeypatch, tmp_path) as base_url:
        with pytest.raises(error.HTTPError) as excinfo:
            urllib_request.urlopen(f"{base_url}/reverse", timeout=2)
        body = excinfo.value.read().decode("utf-8")

    assert excinfo.value.code == 404
    assert json.loads(body)["error"]["code"] == "not_found"


def test_cli_health_and_stdio_compatibility(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["MEDHARNESS_KEYSTORE_ROOT"] = str(tmp_path / "keystore")
    env[server_v2.DEFAULT_REVERSE_TOKEN_ENV] = TOKEN
    health = subprocess.run(
        [sys.executable, str(DESENSITIZE_DIR / "server_v2.py"), "health"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    assert json.loads(health.stdout)["status"] == "ok-v2"

    raw = "SYNTHETIC-PHI-0000000001"
    text = f"patient marker {raw} ok"
    request = {"id": "t2", "method": "desensitize", "params": _request(text, raw)}
    stdio = subprocess.run(
        [sys.executable, str(DESENSITIZE_DIR / "server_v2.py"), "serve", "--stdio"],
        input=json.dumps(request, ensure_ascii=False) + "\n",
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    response = json.loads(stdio.stdout.splitlines()[0])
    assert response["id"] == "t2"
    assert raw not in json.dumps(response, ensure_ascii=False)
