from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "mcp" / "model-router" / "Dockerfile"
REQUIREMENTS = ROOT / "mcp" / "model-router" / "requirements.txt"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _requirements_text() -> str:
    return REQUIREMENTS.read_text(encoding="utf-8")


def test_model_router_dockerfile_is_multi_stage_python_311_slim() -> None:
    text = _dockerfile_text()

    assert "ARG PYTHON_VERSION=3.11" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS builder" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS runtime" in text


def test_model_router_dockerfile_uses_non_root_medharness_user() -> None:
    text = _dockerfile_text()

    assert "groupadd --gid 9000 medharness" in text
    assert "useradd --uid 9000 --gid 9000" in text
    assert "USER medharness:medharness" in text


def test_model_router_dockerfile_has_required_labels_and_args() -> None:
    text = _dockerfile_text()

    assert "ARG VERSION=unknown" in text
    assert "ARG GIT_COMMIT=unknown" in text
    assert 'org.opencontainers.image.title="medharness-model-router"' in text
    assert "org.opencontainers.image.version=$VERSION" in text
    assert "org.opencontainers.image.revision=$GIT_COMMIT" in text
    assert 'org.opencontainers.image.licenses="Apache-2.0"' in text
    assert 'org.opencontainers.image.source="https://github.com/charliehzm/medharness"' in text
    assert 'org.opencontainers.image.vendor="MedHarness"' in text


def test_model_router_dockerfile_healthcheck_calls_server_v2_health() -> None:
    text = _dockerfile_text()

    assert "HEALTHCHECK" in text
    assert "CMD python server_v2.py health || exit 1" in text


def test_model_router_dockerfile_copies_all_runtime_files_with_chown() -> None:
    text = _dockerfile_text()
    expected = (
        "server_v2.py",
        "allowlist.py",
        "heterogeneity.py",
        "limits.py",
        "policy.py",
        "vendor_families.py",
        "vendor_families.yml",
    )

    assert "WORKDIR /app" in text
    for filename in expected:
        assert f"COPY --chown=medharness:medharness mcp/model-router/{filename}" in text


def test_model_router_dockerfile_does_not_copy_legacy_stub_or_allowlist_data() -> None:
    text = _dockerfile_text()

    assert "mcp/model-router/server.py" not in text
    assert "MODEL_ALLOWLIST.json" not in text


def test_model_router_dockerfile_entrypoint_serves_stdio() -> None:
    text = _dockerfile_text()

    assert 'ENTRYPOINT ["python", "server_v2.py"]' in text
    assert 'CMD ["serve", "--stdio"]' in text


def test_model_router_requirements_are_minimal_yaml_slice() -> None:
    lines = [
        line.strip().lower()
        for line in _requirements_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert lines == ["pyyaml>=6.0,<7.0"]


def test_model_router_requirements_do_not_include_heavy_runtime_deps() -> None:
    combined = f"{_dockerfile_text()}\n{_requirements_text()}".lower()

    forbidden = (
        "presidio",
        "cryptography",
        "clickhouse",
        "spacy",
        "jieba",
        "zstandard",
        "faker",
        "httpx",
    )
    for marker in forbidden:
        assert marker not in combined


def test_model_router_dockerfile_does_not_include_dev_deps() -> None:
    combined = f"{_dockerfile_text()}\n{_requirements_text()}".lower()

    forbidden = ("requirements-dev.txt", "pytest", "mkdocs", "ruff", "mypy", "black")
    for marker in forbidden:
        assert marker not in combined


def test_model_router_dockerfile_does_not_expose_secrets() -> None:
    text = _dockerfile_text().lower()

    forbidden = ("env ", "secret", "token", "password", "key=")
    for marker in forbidden:
        assert marker not in text
