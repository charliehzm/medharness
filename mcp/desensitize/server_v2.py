#!/usr/bin/env python3
"""mcp-desensitize v2 · AES-GCM envelope integration."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from crypto_envelope import decrypt_mapping, encrypt_mapping  # noqa: E402
from key_provider import (  # noqa: E402
    ChangeId,
    EncryptedEnvelopeMetadata,
    EncryptionContext,
    KeyId,
    KeyNotFoundError,
    KeyProviderError,
    MapId,
)
from key_provider.file_provider import FileKeyProvider  # noqa: E402
from server import SUBSTITUTIONS  # noqa: E402

DEFAULT_KEY_ID = "active"
DEFAULT_REVERSE_TOKEN_ENV = "COMPLIANCE_REVERSE_TOKEN"
PLACEHOLDER_PREFIX = "PHI"


def _provider() -> FileKeyProvider:
    return FileKeyProvider()


def _safe_error(exc: Exception) -> dict[str, str]:
    return {"type": exc.__class__.__name__, "message": str(exc)}


def _metadata_from_dict(payload: dict[str, Any]) -> EncryptedEnvelopeMetadata:
    try:
        return EncryptedEnvelopeMetadata(
            key_id=KeyId(str(payload["key_id"])),
            algorithm=payload["algorithm"],
            schema_version=str(payload["schema_version"]),
            nonce_b64=str(payload["nonce_b64"]),
            aad_sha256=str(payload["aad_sha256"]),
        )
    except KeyError as exc:
        raise KeyProviderError("missing envelope metadata field") from exc


def _context_from_payload(
    payload: dict[str, Any], metadata: dict[str, Any] | None = None
) -> EncryptionContext:
    key_id = str(payload.get("key_id") or (metadata or {}).get("key_id") or DEFAULT_KEY_ID)
    return EncryptionContext(
        change_id=ChangeId(str(payload.get("change_id", "unknown"))),
        map_id=MapId(str(payload.get("map_id") or uuid.uuid4())),
        key_id=KeyId(key_id),
    )


def _span_text_sha256(text: str, start: int, end: int, provided: str | None) -> str:
    if provided:
        return provided
    return hashlib.sha256(text[start:end].encode("utf-8")).hexdigest()


def _length_preserving_placeholder(entity_type: str, text_sha256: str, length: int) -> str:
    sha8 = text_sha256[:8]
    preferred = f"{{{{ {PLACEHOLDER_PREFIX}_{entity_type}_{sha8} }}}}"
    if len(preferred) == length:
        return preferred
    if len(preferred) < length:
        return preferred + (" " * (length - len(preferred)))
    compact = f"{PLACEHOLDER_PREFIX}_{entity_type}_{sha8}"
    if len(compact) >= length:
        return compact[:length]
    return (compact + ("_" * length))[:length]


def _normalize_spans(request: dict[str, Any], text: str) -> list[dict[str, Any]]:
    spans = request.get("phi_spans")
    if isinstance(spans, list):
        return spans

    detected: list[dict[str, Any]] = []
    for entity_type, pattern, _token_code in SUBSTITUTIONS:
        for match in pattern.finditer(text):
            detected.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "entity_type": entity_type.replace("-", "_").upper(),
                    "score": 0.8,
                    "text_sha256": hashlib.sha256(match.group().encode("utf-8")).hexdigest(),
                }
            )
    return detected


def _build_desensitized_text_and_mapping(
    text: str, spans: list[dict[str, Any]]
) -> tuple[str, dict[str, str]]:
    chars = list(text)
    mapping: dict[str, str] = {}
    consumed_until = 0

    for span in sorted(spans, key=lambda item: (int(item["start"]), int(item["end"]))):
        start = int(span["start"])
        end = int(span["end"])
        if start < consumed_until or start < 0 or end > len(text) or start >= end:
            raise KeyProviderError("invalid or overlapping phi span")

        original = text[start:end]
        entity_type = str(span.get("entity_type", "UNKNOWN")).replace("-", "_").upper()
        text_sha256 = _span_text_sha256(text, start, end, span.get("text_sha256"))
        placeholder = _length_preserving_placeholder(entity_type, text_sha256, end - start)
        chars[start:end] = list(placeholder)
        mapping[placeholder] = original
        consumed_until = end

    desensitized_text = "".join(chars)
    if len(desensitized_text) != len(text):
        raise KeyProviderError("desensitized text length mismatch")
    return desensitized_text, mapping


def _active_key(provider: FileKeyProvider, key_id: str) -> tuple[bytes, int]:
    try:
        key = provider.get_key(key_id)
    except KeyNotFoundError:
        provider.rotate(key_id)
        key = provider.get_key(key_id)
    active_generation = provider.list_generations(key_id)[-1]
    return key, active_generation


def desensitize(request: dict[str, Any], provider: FileKeyProvider | None = None) -> dict[str, Any]:
    provider = provider or _provider()
    text = request.get("text", request.get("payload", ""))
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    context_payload = request.get("context") if isinstance(request.get("context"), dict) else {}
    if "change_id" not in context_payload and "change_id" in request:
        context_payload["change_id"] = request["change_id"]
    if "map_id" not in context_payload:
        context_payload["map_id"] = str(uuid.uuid4())
    if "key_id" not in context_payload:
        context_payload["key_id"] = DEFAULT_KEY_ID

    context = _context_from_payload(context_payload)
    spans = _normalize_spans(request, text)
    desensitized_text, mapping = _build_desensitized_text_and_mapping(text, spans)
    key, key_generation = _active_key(provider, str(context.key_id))
    map_ref, metadata = encrypt_mapping(mapping, key, context)
    metadata_dict = asdict(metadata)
    metadata_dict["key_generation"] = key_generation

    result: dict[str, Any] = {
        "desensitized_text": desensitized_text,
        "map_ref": map_ref,
        "metadata": metadata_dict,
    }
    try:
        if (
            key_generation - provider.list_generations(str(context.key_id))[0] + 1
            >= provider._max_generations
        ):
            result["warning"] = "old key generations must be migrated before prune"
    except Exception:
        pass
    return result


def _reverse_allowed(request: dict[str, Any]) -> bool:
    expected = os.environ.get(DEFAULT_REVERSE_TOKEN_ENV)
    token = request.get("kms_token")
    context = request.get("context")
    if token is None and isinstance(context, dict):
        token = context.get("kms_token")
    return bool(expected) and token == expected


def reverse(request: dict[str, Any], provider: FileKeyProvider | None = None) -> dict[str, Any]:
    if not _reverse_allowed(request):
        return {
            "error": {
                "type": "PermissionError",
                "message": "token invalid or missing; reverse denied",
            }
        }

    provider = provider or _provider()
    try:
        metadata_payload = request.get("metadata")
        if not isinstance(metadata_payload, dict):
            raise KeyProviderError("missing envelope metadata")
        metadata = _metadata_from_dict(metadata_payload)
        context_payload = request.get("context")
        if not isinstance(context_payload, dict):
            raise KeyProviderError("missing reverse context")
        context = _context_from_payload(context_payload, metadata_payload)
        generation = metadata_payload.get("key_generation")
        if generation is None:
            key = provider.get_key(str(context.key_id))
        else:
            key = provider.get_key_by_generation(str(context.key_id), int(generation))
        mapping = decrypt_mapping(str(request.get("map_ref", "")), metadata, key, context)
    except Exception as exc:
        return {"error": _safe_error(exc)}
    return {"mapping": mapping}


def health() -> dict[str, str]:
    return {"status": "ok-v2", "crypto": "AES-256-GCM", "key_provider": "FileKeyProvider"}


def _response_for_request(
    req: dict[str, Any], provider: FileKeyProvider | None = None
) -> dict[str, Any]:
    method = req.get("method")
    params = req.get("params", {})
    if not isinstance(params, dict):
        params = {}
    if method == "desensitize":
        return {"id": req.get("id"), "result": desensitize(params, provider)}
    if method == "reverse":
        return {"id": req.get("id"), "result": reverse(params, provider)}
    if method == "health":
        return {"id": req.get("id"), "result": health()}
    return {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                response = _response_for_request(req)
            except Exception as exc:
                response = {"id": None, "error": _safe_error(exc)}
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0

    cmd = sys.argv[1] if len(sys.argv) > 1 else "desensitize"
    if cmd == "health":
        print(json.dumps(health(), ensure_ascii=False))
        return 0
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    if cmd == "desensitize":
        print(json.dumps(desensitize(req), ensure_ascii=False))
        return 0
    if cmd == "reverse":
        result = reverse(req)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if "error" in result else 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


desensitize_v2 = desensitize


if __name__ == "__main__":
    sys.exit(main())
