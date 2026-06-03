"""Layer 3 — desensitize encrypt path against the LIVE ClickHouse _phi_lookup.

Drives the real desensitize /encrypt (via the a0 container) with synthetic PHI and
asserts: the prompt is redacted, the encrypted envelope is persisted to the live
_phi_lookup keystore with a verifiable ciphertext integrity hash, and the stored
row contains only ENCRYPTED metadata — never the raw identifier. (The decrypt
round-trip itself is covered by the offline crypto-envelope unit tests.)
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid

SYNTHETIC_ID = "110101199001011237"  # valid-checksum synthetic CN-ID from the unit corpus
PHI_TEXT = f"请核对身份证 {SYNTHETIC_ID}。"
_ID_START = PHI_TEXT.index(SYNTHETIC_ID)


def test_encrypt_redacts_and_persists_envelope(mcp_post, ch_query, no_phi) -> None:
    change_id = f"rt-{uuid.uuid4().hex[:8]}"
    status, resp = mcp_post(
        "desensitize",
        "/encrypt",
        {
            "text": PHI_TEXT,
            "phi_spans": [{"type": "CN_ID", "start": _ID_START, "end": _ID_START + len(SYNTHETIC_ID)}],
            "context": {"change_id": change_id, "map_id": "rt-probe"},
        },
    )
    assert status == 200, resp
    assert resp.get("desensitized") is True
    # the redacted prompt must NOT carry the raw identifier
    assert SYNTHETIC_ID not in resp.get("desensitized_text", ""), resp.get("desensitized_text")

    # the envelope is keyed in _phi_lookup by its ciphertext ref (the response map_ref)
    map_ref = resp["map_ref"]
    rows = ch_query("SELECT * FROM _phi_lookup WHERE ciphertext_b64 = '%s'" % map_ref)
    assert rows, f"envelope not persisted to live _phi_lookup for map_ref={map_ref}"
    row = rows[0]
    assert row["algorithm"] == "AES-256-GCM"
    # ciphertext integrity: the stored sha256 matches sha256(decoded ciphertext)
    ciphertext = base64.urlsafe_b64decode(row["ciphertext_b64"] + "=" * (-len(row["ciphertext_b64"]) % 4))
    assert hashlib.sha256(ciphertext).hexdigest() == row["ciphertext_sha256"]
    # the keystore stores only encrypted metadata — the raw PHI must never appear
    serialized = json.dumps(rows, ensure_ascii=False)
    assert SYNTHETIC_ID not in serialized, "RAW PHI persisted in the keystore"
    no_phi(serialized, "live _phi_lookup envelope")


def test_phi_lookup_schema_exists(ch_query) -> None:
    rows = ch_query(
        "SELECT name FROM system.tables WHERE database='medharness' AND name='_phi_lookup'"
    )
    assert any(r["name"] == "_phi_lookup" for r in rows), "phi_lookup keystore schema missing"
