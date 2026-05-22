from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "desensitize"))

from crypto_envelope import decrypt_mapping, encrypt_mapping, metadata_to_dict  # noqa: E402
from key_provider import ChangeId, EncryptionContext, KeyId, KeyProviderError, MapId  # noqa: E402


def _context(
    *,
    change_id: str = "change-t2",
    map_id: str = "map-synthetic",
    key_id: str = "active",
) -> EncryptionContext:
    return EncryptionContext(
        change_id=ChangeId(change_id),
        map_id=MapId(map_id),
        key_id=KeyId(key_id),
    )


def test_roundtrip_succeeds_with_aes256_gcm() -> None:
    key = b"k" * 32
    mapping = {"{{ ID_ABCD }}": "synthetic-id-001", "shifted_date": "2026-05-22"}
    context = _context()

    ciphertext, metadata = encrypt_mapping(mapping, key, context)
    restored = decrypt_mapping(ciphertext, metadata, key, context)

    assert restored == mapping
    assert metadata.algorithm == "AES-256-GCM"
    assert len(metadata.aad_sha256) == 64


def test_encrypt_uses_fresh_96_bit_nonce() -> None:
    key = b"k" * 32
    mapping = {"{{ ID_ABCD }}": "synthetic-id-001"}
    context = _context()

    ciphertext_a, metadata_a = encrypt_mapping(mapping, key, context)
    ciphertext_b, metadata_b = encrypt_mapping(mapping, key, context)

    assert metadata_a.nonce_b64 != metadata_b.nonce_b64
    assert ciphertext_a != ciphertext_b


def test_aad_tamper_fails_closed() -> None:
    key = b"k" * 32
    mapping = {"{{ ID_ABCD }}": "synthetic-id-001"}
    context = _context()
    ciphertext, metadata = encrypt_mapping(mapping, key, context)
    tampered_context = _context(change_id="other-change")

    with pytest.raises(KeyProviderError, match="AAD metadata mismatch"):
        decrypt_mapping(ciphertext, metadata, key, tampered_context)


def test_wrong_key_fails_closed() -> None:
    key = b"k" * 32
    wrong_key = b"w" * 32
    mapping = {"{{ ID_ABCD }}": "synthetic-id-001"}
    context = _context()
    ciphertext, metadata = encrypt_mapping(mapping, key, context)

    with pytest.raises(KeyProviderError, match="authentication failed"):
        decrypt_mapping(ciphertext, metadata, wrong_key, context)


def test_nonce_reuse_cannot_decrypt_different_ciphertext() -> None:
    key = b"k" * 32
    context = _context()
    ciphertext_a, metadata_a = encrypt_mapping({"a": "synthetic-a"}, key, context)
    ciphertext_b, _metadata_b = encrypt_mapping({"b": "synthetic-b"}, key, context)
    mismatched_metadata = replace(metadata_a, nonce_b64=metadata_a.nonce_b64)

    with pytest.raises(KeyProviderError, match="authentication failed"):
        decrypt_mapping(ciphertext_b, mismatched_metadata, key, context)

    assert decrypt_mapping(ciphertext_a, metadata_a, key, context) == {"a": "synthetic-a"}


def test_bad_key_length_fails_closed() -> None:
    context = _context()

    with pytest.raises(KeyProviderError, match="32 bytes"):
        encrypt_mapping({"a": "b"}, b"short", context)

    with pytest.raises(KeyProviderError, match="32 bytes"):
        decrypt_mapping(
            "ciphertext",
            replace(encrypt_mapping({"a": "b"}, b"k" * 32, context)[1]),
            b"short",
            context,
        )


def test_metadata_serialization_contains_no_plaintext_or_key_bytes() -> None:
    key = b"k" * 32
    mapping = {"{{ ID_ABCD }}": "synthetic-id-001"}
    context = _context()
    ciphertext, metadata = encrypt_mapping(mapping, key, context)
    payload = json.dumps({"ciphertext": ciphertext, "metadata": metadata_to_dict(metadata)})

    assert "synthetic-id-001" not in payload
    assert "kkkk" not in payload
