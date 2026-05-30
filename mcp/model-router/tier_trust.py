"""Tier-trust boundary for model-router (REVIEW-r2 B1 / ADR-18 §3).

The data tier / lane fields (``data_level``, ``desensitized``,
``caller_vendor_family``) decide whether L4 PHI may leave the gate. A *caller*
must never be able to self-assert them, otherwise L4 can masquerade as L1 and
ride the cheap / overseas lane.

So those fields are only trusted when accompanied by an HMAC signature minted by
the gate middleware (the holder of ``MODEL_ROUTER_TIER_SECRET``). PolicyCore
rejects any request whose tier is not signed (fail-closed): no secret configured
or no/invalid signature => ``tier_trusted = False`` => deny.

In v0.5 the signer is the trusted test/dev harness; in Phase A it is the new-api
built-in Go middleware (after phi-detect + desensitize determine the real tier).
"""

from __future__ import annotations

import hashlib
import hmac
import os

# Fields whose value must be attested by the middleware, not the caller.
TIER_FIELDS: tuple[str, ...] = (
    "model_id",
    "agent_role",
    "data_level",
    "change_id",
    "caller_vendor_family",
    "desensitized",
)

SECRET_ENV = "MODEL_ROUTER_TIER_SECRET"


def _canonical(payload: dict[str, object]) -> bytes:
    """Stable byte encoding of the tier fields for signing/verification."""
    parts: list[str] = []
    for key in TIER_FIELDS:
        value = payload.get(key, "")
        if isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"{key}={value}")
    return "\n".join(parts).encode("utf-8")


def load_secret() -> bytes | None:
    """HMAC secret from env, or ``None`` (=> fail-closed, nothing is trusted)."""
    secret = os.environ.get(SECRET_ENV)
    return secret.encode("utf-8") if secret else None


def sign_tier(payload: dict[str, object], secret: bytes) -> str:
    """Mint the tier signature (middleware / trusted issuer side)."""
    return hmac.new(secret, _canonical(payload), hashlib.sha256).hexdigest()


def verify_tier(
    payload: dict[str, object],
    signature: str | None,
    secret: bytes | None,
) -> bool:
    """Fail-closed verify: no secret or no/invalid signature => not trusted."""
    if not secret or not signature:
        return False
    expected = sign_tier(payload, secret)
    return hmac.compare_digest(expected, str(signature))
