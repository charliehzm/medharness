"""Key provider contracts for mcp-desensitize.

This module is intentionally implementation-free. Concrete providers must never
log key bytes, plaintext mapping values, or customer identifiers in exceptions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, NewType

KeyId = NewType("KeyId", str)
MapId = NewType("MapId", str)
ChangeId = NewType("ChangeId", str)
Algorithm = Literal["AES-256-GCM"]


class KeyProviderError(RuntimeError):
    """Base error for key provider failures.

    Error messages must stay metadata-only: include key ids, provider names, and
    safe state labels, but never key bytes or plaintext reverse mappings.
    """


class KeyNotFoundError(KeyProviderError):
    """Raised when a key id cannot be resolved."""


class KeyRotationError(KeyProviderError):
    """Raised when a provider cannot rotate a key safely."""


class KeyPermissionError(KeyProviderError):
    """Raised when key storage permissions are unsafe."""


@dataclass(frozen=True)
class KeyMetadata:
    """Metadata about a key without exposing the key bytes."""

    key_id: KeyId
    provider: str
    created_at: str | None = None
    active: bool = True
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EncryptionContext:
    """Authenticated context bound to encrypted reverse-mapping envelopes."""

    change_id: ChangeId
    map_id: MapId
    key_id: KeyId
    algorithm: Algorithm = "AES-256-GCM"
    schema_version: str = "T2.envelope.v1"


@dataclass(frozen=True)
class PhiSpan:
    """Detector span shape consumed by desensitize implementations."""

    start: int
    end: int
    entity_type: str
    score: float
    text_sha256: str


@dataclass(frozen=True)
class EncryptedEnvelopeMetadata:
    """Serializable metadata needed to choose the correct decrypt key."""

    key_id: KeyId
    algorithm: Algorithm
    schema_version: str
    nonce_b64: str
    aad_sha256: str


class KeyProvider(ABC):
    """Abstract provider for local or external key custody.

    Implementations return raw key bytes to the caller only for in-process
    encryption / decryption. They must not print, log, cache in repr strings, or
    place key bytes in exception messages.
    """

    @abstractmethod
    def get_key(self, key_id: KeyId | str) -> bytes:
        """Return raw key bytes for ``key_id`` or fail closed."""

    @abstractmethod
    def rotate(self, key_id: KeyId | str) -> bytes:
        """Create and activate a new key generation for ``key_id``."""

    @abstractmethod
    def list_keys(self) -> list[KeyId]:
        """Return safe key ids available to this provider."""
