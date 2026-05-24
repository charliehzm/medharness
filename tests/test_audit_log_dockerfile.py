from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "mcp" / "audit-log" / "Dockerfile"
REQUIREMENTS = ROOT / "mcp" / "audit-log" / "requirements.txt"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _requirements_text() -> str:
    return REQUIREMENTS.read_text(encoding="utf-8")


def _requirement_lines() -> list[str]:
    return [
        line.strip().lower()
        for line in _requirements_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_audit_log_dockerfile_is_multi_stage_python_311_slim() -> None:
    text = _dockerfile_text()

    assert "ARG PYTHON_VERSION=3.11" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS builder" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS runtime" in text


def test_audit_log_dockerfile_uses_non_root_medharness_user() -> None:
    text = _dockerfile_text()

    assert "groupadd --gid 9000 medharness" in text
    assert "useradd --uid 9000 --gid 9000" in text
    assert "USER medharness:medharness" in text


def test_audit_log_dockerfile_has_required_labels_and_args() -> None:
    text = _dockerfile_text()

    assert "ARG VERSION=unknown" in text
    assert "ARG GIT_COMMIT=unknown" in text
    assert 'org.opencontainers.image.title="medharness-audit-log"' in text
    assert "org.opencontainers.image.version=$VERSION" in text
    assert "org.opencontainers.image.revision=$GIT_COMMIT" in text
    assert 'org.opencontainers.image.licenses="Apache-2.0"' in text
    assert 'org.opencontainers.image.source="https://github.com/charliehzm/medharness"' in text
    assert 'org.opencontainers.image.vendor="MedHarness"' in text


def test_audit_log_dockerfile_healthcheck_is_import_smoke_not_cli() -> None:
    text = _dockerfile_text()

    assert "HEALTHCHECK" in text
    assert 'CMD python -c "from server_v2 import AuditLogServerV2" || exit 1' in text
    assert "python server_v2.py health" not in text


def test_audit_log_dockerfile_copies_v2_runtime_files_with_chown() -> None:
    text = _dockerfile_text()
    expected = (
        "server_v2.py",
        "clickhouse_writer.py",
        "fallback_writer.py",
        "hashchain.py",
        "sql/audit_log.sql",
    )

    assert "WORKDIR /app" in text
    for filename in expected:
        assert f"COPY --chown=medharness:medharness mcp/audit-log/{filename}" in text


def test_audit_log_dockerfile_does_not_copy_legacy_stub_or_event_types() -> None:
    text = _dockerfile_text()

    assert "mcp/audit-log/server.py" not in text
    assert "event_types.yml" not in text


def test_audit_log_dockerfile_entrypoint_is_sleep_loop_for_v0_5_0() -> None:
    text = _dockerfile_text()

    assert 'ENTRYPOINT ["python"]' in text
    assert "time.sleep(86400)" in text
    assert "v0.6+ adds CLI" in text


def test_audit_log_requirements_are_comment_only_mock_mode() -> None:
    text = _requirements_text().lower()

    assert _requirement_lines() == []
    assert "clickhouse-connect intentionally not installed" in text
    assert "v0.6+ follow-up" in text


def test_audit_log_requirements_exclude_clickhouse_connect_for_v0_5_0() -> None:
    dockerfile = _dockerfile_text().lower()
    requirement_lines = _requirement_lines()

    assert "clickhouse-connect>=" not in dockerfile
    assert "clickhouse_connect" not in dockerfile
    assert "clickhouse connect" not in dockerfile
    assert all("clickhouse" not in line for line in requirement_lines)


def test_audit_log_requirements_exclude_dev_and_heavy_deps() -> None:
    combined = f"{_dockerfile_text()}\n{_requirements_text()}".lower()

    forbidden = (
        "requirements-dev.txt",
        "pytest",
        "mkdocs",
        "ruff",
        "presidio",
        "cryptography",
        "spacy",
        "jieba",
        "httpx",
    )
    for marker in forbidden:
        assert marker not in combined


def test_audit_log_dockerfile_does_not_expose_secrets() -> None:
    text = _dockerfile_text().lower()

    forbidden = ("env ", "secret", "token", "password", "key=")
    for marker in forbidden:
        assert marker not in text


def test_audit_log_dockerfile_copies_sql_schema() -> None:
    text = _dockerfile_text()

    assert "mcp/audit-log/sql/audit_log.sql /app/sql/audit_log.sql" in text
