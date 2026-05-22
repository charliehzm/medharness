from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "mcp" / "desensitize" / "sql" / "phi_lookup.sql"


def _load_sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def _table_block(sql: str) -> str:
    match = re.search(r"CREATE TABLE _phi_lookup\s*\((.*?)\)\s*ENGINE", sql, re.S)
    assert match, "CREATE TABLE _phi_lookup block not found"
    return match.group(1)


def _column_map(sql: str) -> dict[str, str]:
    columns: dict[str, str] = {}
    for raw_line in _table_block(sql).splitlines():
        line = raw_line.split("--", 1)[0].strip().rstrip(",")
        if not line:
            continue
        match = re.match(
            r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<type>.+?)(?:\s+DEFAULT\s+(?P<default>.+))?$",
            line,
        )
        assert match, f"unparseable column line: {raw_line!r}"
        columns[match.group("name")] = " ".join(match.group("type").split())
    return columns


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


def test_phi_lookup_schema_has_required_shape_and_clauses() -> None:
    sql = _load_sql()
    columns = _column_map(sql)

    assert columns == {
        "map_id": "String",
        "change_id": "LowCardinality(String)",
        "key_id": "LowCardinality(String)",
        "key_generation": "UInt32",
        "algorithm": "LowCardinality(String)",
        "schema_version": "LowCardinality(String)",
        "nonce_b64": "FixedString(16)",
        "aad_sha256": "FixedString(64)",
        "ciphertext_b64": "String",
        "ciphertext_sha256": "FixedString(64)",
        "created_at": "DateTime64(3, 'UTC')",
        "retention_until": "DateTime64(3, 'UTC')",
        "inserted_at": "DateTime64(3)",
    }

    required_clauses = [
        "ENGINE = MergeTree",
        "PARTITION BY toYYYYMM(created_at)",
        "ORDER BY (created_at, change_id, map_id)",
        "TTL retention_until + INTERVAL 1 YEAR",
        "SETTINGS index_granularity = 8192",
        "GRANT INSERT, SELECT ON _phi_lookup TO medharness_desensitize_writer;",
        "REVOKE ALTER UPDATE, ALTER DELETE FROM medharness_desensitize_writer;",
    ]
    for clause in required_clauses:
        assert clause in sql

    lower_sql = sql.lower()
    for forbidden in ("original", "raw_text", "patient_name", "phone"):
        assert forbidden not in lower_sql

    assert "real phi" not in lower_sql
    assert "customer markers" not in lower_sql


def test_phi_lookup_schema_is_sqlite_parseable_after_clickhouse_clause_stripping() -> None:
    sql = _load_sql()
    simplified = _sqlite_simplified_sql(sql)

    with sqlite3.connect(":memory:") as conn:
        conn.executescript(simplified)

    assert "CREATE TABLE _phi_lookup" in simplified
    assert "ENGINE = MergeTree" not in simplified


def test_phi_lookup_schema_comments_do_not_include_sensitive_examples() -> None:
    sql = _load_sql()
    comment_lines = [line.strip() for line in sql.splitlines() if line.lstrip().startswith("--")]
    joined_comments = "\n".join(comment_lines).lower()

    for forbidden in ("patient_name", "raw_text", "original", "phone"):
        assert forbidden not in joined_comments

    assert "no plaintext phi values are stored here." in joined_comments
