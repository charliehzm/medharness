"""AES-256-GCM envelope helpers for encrypted reverse mappings."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import asdict
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from key_provider import EncryptedEnvelopeMetadata, EncryptionContext, KeyProviderError

AES256_GCM_KEY_BYTES = 32
AESGCM_NONCE_BYTES = 12


def _validate_key(key: bytes) -> None:
    if len(key) != AES256_GCM_KEY_BYTES:
        raise KeyProviderError("AES-256-GCM key must be 32 bytes")


def canonical_aad(context: EncryptionContext) -> bytes:
    """Return canonical authenticated data for ``context``."""

    payload = {
        "algorithm": context.algorithm,
        "change_id": str(context.change_id),
        "key_id": str(context.key_id),
        "map_id": str(context.map_id),
        "schema_version": context.schema_version,
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def aad_sha256(context: EncryptionContext) -> str:
    """Return the SHA-256 digest of ``context`` AAD."""

    return hashlib.sha256(canonical_aad(context)).hexdigest()


def encrypt_mapping(
    mapping: dict[str, Any],
    key: bytes,
    context: EncryptionContext,
) -> tuple[str, EncryptedEnvelopeMetadata]:
    """Encrypt a reverse mapping using AES-256-GCM.

    The returned ciphertext is URL-safe base64 over the AESGCM output bytes,
    which include the authentication tag appended by ``cryptography``.
    """

    _validate_key(key)
    nonce = secrets.token_bytes(AESGCM_NONCE_BYTES)
    plaintext = json.dumps(mapping, ensure_ascii=False, sort_keys=True).encode("utf-8")
    aad = canonical_aad(context)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    metadata = EncryptedEnvelopeMetadata(
        key_id=context.key_id,
        algorithm=context.algorithm,
        schema_version=context.schema_version,
        nonce_b64=base64.urlsafe_b64encode(nonce).decode("ascii"),
        aad_sha256=hashlib.sha256(aad).hexdigest(),
    )
    return base64.urlsafe_b64encode(ciphertext).decode("ascii"), metadata


def decrypt_mapping(
    ciphertext_b64: str,
    metadata: EncryptedEnvelopeMetadata,
    key: bytes,
    context: EncryptionContext,
) -> dict[str, Any]:
    """Decrypt an AES-256-GCM envelope or fail closed."""

    _validate_key(key)
    if metadata.aad_sha256 != aad_sha256(context):
        raise KeyProviderError("AAD metadata mismatch")
    if (
        metadata.key_id != context.key_id
        or metadata.algorithm != context.algorithm
        or metadata.schema_version != context.schema_version
    ):
        raise KeyProviderError("envelope metadata mismatch")
    try:
        nonce = base64.urlsafe_b64decode(metadata.nonce_b64.encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
    except Exception as exc:
        raise KeyProviderError("invalid encrypted envelope encoding") from exc
    if len(nonce) != AESGCM_NONCE_BYTES:
        raise KeyProviderError("invalid AES-GCM nonce length")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, canonical_aad(context))
    except InvalidTag as exc:
        raise KeyProviderError("AES-GCM authentication failed") from exc
    try:
        value = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise KeyProviderError("invalid decrypted mapping payload") from exc
    if not isinstance(value, dict):
        raise KeyProviderError("decrypted mapping payload must be an object")
    return value


def metadata_to_dict(metadata: EncryptedEnvelopeMetadata) -> dict[str, str]:
    """Serialize envelope metadata without key bytes or plaintext."""

    return asdict(metadata)
