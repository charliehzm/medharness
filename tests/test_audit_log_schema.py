from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "mcp" / "audit-log" / "sql" / "audit_log.sql"


def _load_sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def _table_block(sql: str) -> str:
    match = re.search(r"CREATE TABLE _audit_log\s*\((.*?)\)\s*ENGINE", sql, re.S)
    assert match, "CREATE TABLE _audit_log block not found"
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
        r"GRANT\s+INSERT,\s+SELECT\s+ON\s+_audit_log\s+TO\s+medharness_audit_writer;",
        "",
        simplified,
    )
    simplified = re.sub(
        r"REVOKE\s+ALTER\s+UPDATE,\s+ALTER\s+DELETE\s+FROM\s+medharness_audit_writer;",
        "",
        simplified,
    )
    simplified = re.sub(r"\)\s*ENGINE\s*=\s*MergeTree.*?;", ");", simplified, flags=re.S)
    simplified = simplified.replace("Array(LowCardinality(String))", "TEXT")
    simplified = simplified.replace("LowCardinality(String)", "TEXT")
    simplified = simplified.replace("FixedString(64)", "TEXT")
    simplified = simplified.replace("DateTime64(3, 'UTC')", "TEXT")
    simplified = simplified.replace("DateTime64(3)", "TEXT")
    simplified = simplified.replace("Nullable(UInt8)", "INTEGER")
    simplified = simplified.replace("Nullable(String)", "TEXT")
    simplified = simplified.replace("UUID", "TEXT")
    simplified = simplified.replace("UInt64", "INTEGER")
    simplified = simplified.replace("UInt8", "INTEGER")
    simplified = simplified.replace("Float32", "REAL")
    simplified = simplified.replace("String", "TEXT")
    simplified = simplified.replace(" DEFAULT now64()", "")
    return simplified


def test_audit_log_schema_has_required_shape_and_clauses() -> None:
    sql = _load_sql()
    columns = _column_map(sql)

    assert columns == {
        "event_id": "UUID",
        "timestamp": "DateTime64(3, 'UTC')",
        "actor_agent_role": "LowCardinality(String)",
        "actor_model_id": "String",
        "actor_vendor_family": "LowCardinality(String)",
        "actor_session_id": "String",
        "action_tool": "String",
        "action_skill": "Nullable(String)",
        "action_operation": "LowCardinality(String)",
        "context_change_id": "Nullable(String)",
        "context_step": "Nullable(UInt8)",
        "context_data_levels": "Array(LowCardinality(String))",
        "result_status": "LowCardinality(String)",
        "result_reason": "Nullable(String)",
        "result_duration_ms": "Float32",
        "input_hash": "FixedString(64)",
        "output_hash": "FixedString(64)",
        "prev_hash": "FixedString(64)",
        "current_hash": "FixedString(64)",
        "row_id": "UInt64",
        "inserted_at": "DateTime64(3)",
    }

    required_clauses = [
        "ENGINE = MergeTree",
        "PARTITION BY toYYYYMM(timestamp)",
        "ORDER BY (timestamp, row_id)",
        "TTL timestamp + INTERVAL 7 YEAR",
        "SETTINGS index_granularity = 8192",
        "GRANT INSERT, SELECT ON _audit_log TO medharness_audit_writer;",
        "REVOKE ALTER UPDATE, ALTER DELETE FROM medharness_audit_writer;",
    ]
    for clause in required_clauses:
        assert clause in sql

    lower_sql = sql.lower()
    for forbidden in ("prompt", "raw_text", "patient_name", "phone"):
        assert forbidden not in lower_sql

    assert "no plaintext request, response, or phi values are stored here." in lower_sql


def test_audit_log_schema_is_sqlite_parseable_after_clickhouse_clause_stripping() -> None:
    sql = _load_sql()
    simplified = _sqlite_simplified_sql(sql)

    with sqlite3.connect(":memory:") as conn:
        conn.executescript(simplified)

    assert "CREATE TABLE _audit_log" in simplified
    assert "ENGINE = MergeTree" not in simplified


def test_audit_log_schema_does_not_expose_prompt_like_columns_or_plaintext_examples() -> None:
    sql = _load_sql()
    columns = _column_map(sql)
    comment_lines = [line.strip() for line in sql.splitlines() if line.lstrip().startswith("--")]
    joined_comments = "\n".join(comment_lines).lower()

    assert "prompt" not in columns
    for forbidden in ("real phi", "patient_name", "raw_text", "phone"):
        assert forbidden not in joined_comments
