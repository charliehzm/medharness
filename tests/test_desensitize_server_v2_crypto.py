from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

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
