from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESENSITIZE_DIR = ROOT / "mcp" / "desensitize"
PHI_LOOKUP_SQL = DESENSITIZE_DIR / "sql" / "phi_lookup.sql"
sys.path.insert(0, str(DESENSITIZE_DIR))

import server_v2  # noqa: E402
from key_provider.file_provider import FileKeyProvider  # noqa: E402

TOKEN = "synthetic-token"
CHANGE_ID = "change-t2-integration"
KEY_ID = "active"


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


def _desensitize_request(text: str, raw: str, map_id: str) -> dict[str, object]:
    return {
        "text": text,
        "phi_spans": [_span(text, raw)],
        "context": {"change_id": CHANGE_ID, "map_id": map_id, "key_id": KEY_ID},
    }


def _reverse_request(row: sqlite3.Row) -> dict[str, object]:
    metadata = {
        "key_id": row["key_id"],
        "algorithm": row["algorithm"],
        "schema_version": row["schema_version"],
        "nonce_b64": row["nonce_b64"],
        "aad_sha256": row["aad_sha256"],
        "key_generation": row["key_generation"],
    }
    return {
        "map_ref": row["ciphertext_b64"],
        "metadata": metadata,
        "context": {
            "change_id": row["change_id"],
            "map_id": row["map_id"],
            "key_id": row["key_id"],
        },
        "kms_token": TOKEN,
    }


def _sqlite_simplified_sql(sql: str) -> str:
    simplified = sql
    simplified = re.sub(r"--.*$", "", simplified, flags=re.M)
    simplified = re.sub(
        r"GRANT\s+INSERT,\s+SELECT\s+ON\s+_phi_lookup\s+TO\s+medharness_desensitize_writer;",
        "",
        simplified,
    )
    simplified = re.sub(
        r"REVOKE\s+ALTER\s+UPDATE,\s+ALTER\s+DELETE\s+FROM\s+medharness_desensitize_writer;",
        "",
        simplified,
    )
    simplified = re.sub(r"\)\s*ENGINE\s*=\s*MergeTree.*?;", ");", simplified, flags=re.S)
    simplified = simplified.replace("LowCardinality(String)", "TEXT")
    simplified = simplified.replace("FixedString(16)", "TEXT")
    simplified = simplified.replace("FixedString(64)", "TEXT")
    simplified = simplified.replace("DateTime64(3, 'UTC')", "TEXT")
    simplified = simplified.replace("DateTime64(3)", "TEXT")
    simplified = simplified.replace(" DEFAULT now64()", "")
    simplified = simplified.replace("UInt32", "INTEGER")
    simplified = simplified.replace("String", "TEXT")
    return simplified


def _sqlite_phi_lookup() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_sqlite_simplified_sql(PHI_LOOKUP_SQL.read_text(encoding="utf-8")))
    return conn


def _persist_envelope(
    conn: sqlite3.Connection,
    *,
    map_id: str,
    result: dict[str, Any],
) -> None:
    metadata = result["metadata"]
    ciphertext = base64.urlsafe_b64decode(result["map_ref"].encode("ascii"))
    now = datetime.now(timezone.utc)
    conn.execute(
        """
        INSERT INTO _phi_lookup (
          map_id, change_id, key_id, key_generation, algorithm, schema_version,
          nonce_b64, aad_sha256, ciphertext_b64, ciphertext_sha256,
          created_at, retention_until, inserted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            map_id,
            CHANGE_ID,
            metadata["key_id"],
            metadata["key_generation"],
            metadata["algorithm"],
            metadata["schema_version"],
            metadata["nonce_b64"],
            metadata["aad_sha256"],
            result["map_ref"],
            hashlib.sha256(ciphertext).hexdigest(),
            now.isoformat(),
            (now + timedelta(days=365 * 6)).isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()


def _lookup(conn: sqlite3.Connection, map_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM _phi_lookup WHERE map_id = ?", (map_id,)).fetchone()
    assert row is not None
    return row


def _desensitize_and_persist(
    conn: sqlite3.Connection,
    provider: FileKeyProvider,
    *,
    raw: str,
    map_id: str,
) -> dict[str, Any]:
    text = f"synthetic patient marker {raw} ok"
    result = server_v2.desensitize(_desensitize_request(text, raw, map_id), provider)
    _persist_envelope(conn, map_id=map_id, result=result)
    return result


def _json_payload(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def test_scenario_a_roundtrip_persists_phi_lookup_and_reverses(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    conn = _sqlite_phi_lookup()
    raw = "SYNTHETIC-PHI-T2-A-0001"
    result = _desensitize_and_persist(conn, provider, raw=raw, map_id="map-t2-a")

    row = _lookup(conn, "map-t2-a")
    reverse = server_v2.reverse(_reverse_request(row), provider)

    assert row["algorithm"] == "AES-256-GCM"
    assert row["key_generation"] == 0
    assert len(row["nonce_b64"]) == 16
    assert len(row["aad_sha256"]) == 64
    assert len(row["ciphertext_sha256"]) == 64
    assert reverse["mapping"]
    assert list(reverse["mapping"].values()) == [raw]
    assert raw not in _json_payload(result)
    assert raw not in result["desensitized_text"]


def test_scenario_b_rotation_preserves_old_and_active_envelopes(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    conn = _sqlite_phi_lookup()
    raw_gen0 = "SYNTHETIC-PHI-T2-B-0001"
    raw_gen1 = "SYNTHETIC-PHI-T2-B-0002"

    _desensitize_and_persist(conn, provider, raw=raw_gen0, map_id="map-t2-b-gen0")
    provider.rotate(KEY_ID)
    _desensitize_and_persist(conn, provider, raw=raw_gen1, map_id="map-t2-b-gen1")

    row_gen0 = _lookup(conn, "map-t2-b-gen0")
    row_gen1 = _lookup(conn, "map-t2-b-gen1")
    reverse_gen0 = server_v2.reverse(_reverse_request(row_gen0), provider)
    reverse_gen1 = server_v2.reverse(_reverse_request(row_gen1), provider)

    assert provider.max_generations == 6
    assert row_gen0["key_generation"] == 0
    assert row_gen1["key_generation"] == 1
    assert list(reverse_gen0["mapping"].values()) == [raw_gen0]
    assert list(reverse_gen1["mapping"].values()) == [raw_gen1]


def test_scenario_c_pruned_generation_returns_key_not_found(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore", max_generations=2)
    conn = _sqlite_phi_lookup()
    raw = "SYNTHETIC-PHI-T2-C-0001"

    _desensitize_and_persist(conn, provider, raw=raw, map_id="map-t2-c-gen0")
    provider.rotate(KEY_ID)
    provider.rotate(KEY_ID)
    provider.rotate(KEY_ID)

    reverse = server_v2.reverse(_reverse_request(_lookup(conn, "map-t2-c-gen0")), provider)

    assert provider.max_generations == 2
    assert reverse["error"]["type"] == "KeyNotFoundError"
    assert raw not in _json_payload(reverse)


def test_scenario_d_chmod_tamper_fails_closed_during_reverse(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    conn = _sqlite_phi_lookup()
    raw = "SYNTHETIC-PHI-T2-D-0001"

    _desensitize_and_persist(conn, provider, raw=raw, map_id="map-t2-d")
    key_path = tmp_path / "keystore" / "active.0.key"
    key_path.chmod(0o644)
    reverse = server_v2.reverse(_reverse_request(_lookup(conn, "map-t2-d")), provider)

    assert key_path.stat().st_mode & 0o777 == 0o644
    assert reverse["error"]["type"] == "KeyPermissionError"
    assert raw not in _json_payload(reverse)


def test_scenario_e_no_raw_phi_leaks_from_desensitize_or_denied_reverse(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(server_v2.DEFAULT_REVERSE_TOKEN_ENV, TOKEN)
    provider = FileKeyProvider(tmp_path / "keystore")
    conn = _sqlite_phi_lookup()
    raw = "SYNTHETIC-PHI-T2-E-0001"
    result = _desensitize_and_persist(conn, provider, raw=raw, map_id="map-t2-e")
    denied_request = _reverse_request(_lookup(conn, "map-t2-e"))
    denied_request["kms_token"] = "wrong-token"

    denied = server_v2.reverse(denied_request, provider)

    assert raw not in _json_payload(result)
    assert raw not in result["desensitized_text"]
    assert denied["error"]["type"] == "PermissionError"
    assert raw not in _json_payload(denied)
