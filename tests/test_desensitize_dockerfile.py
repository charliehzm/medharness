from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESENSITIZE_DIR = ROOT / "mcp" / "desensitize"
DOCKERFILE = DESENSITIZE_DIR / "Dockerfile"
REQUIREMENTS = DESENSITIZE_DIR / "requirements.txt"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _requirements_text() -> str:
    return REQUIREMENTS.read_text(encoding="utf-8")


def test_desensitize_dockerfile_is_multi_stage_python_311_slim() -> None:
    text = _dockerfile_text()

    assert "ARG PYTHON_VERSION=3.11" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS builder" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS runtime" in text


def test_desensitize_dockerfile_uses_non_root_medharness_user() -> None:
    text = _dockerfile_text()

    assert "groupadd --gid 9000 medharness" in text
    assert "useradd --uid 9000 --gid 9000" in text
    assert "USER medharness:medharness" in text


def test_desensitize_dockerfile_has_required_labels_and_args() -> None:
    text = _dockerfile_text()

    assert "ARG VERSION=unknown" in text
    assert "ARG GIT_COMMIT=unknown" in text
    assert 'org.opencontainers.image.title="medharness-desensitize"' in text
    assert "org.opencontainers.image.version=$VERSION" in text
    assert "org.opencontainers.image.revision=$GIT_COMMIT" in text
    assert 'org.opencontainers.image.licenses="Apache-2.0"' in text
    assert 'org.opencontainers.image.source="https://github.com/charliehzm/medharness"' in text
    assert 'org.opencontainers.image.vendor="MedHarness"' in text


def test_desensitize_dockerfile_healthcheck_calls_server_v2_health() -> None:
    text = _dockerfile_text()

    assert "HEALTHCHECK" in text
    assert "CMD python server_v2.py health || exit 1" in text


def test_desensitize_dockerfile_copies_runtime_files_with_chown() -> None:
    text = _dockerfile_text()

    assert "WORKDIR /app" in text
    assert "COPY --chown=medharness:medharness mcp/desensitize/server_v2.py" in text
    assert "COPY --chown=medharness:medharness mcp/desensitize/server.py" in text
    assert "COPY --chown=medharness:medharness mcp/desensitize/crypto_envelope.py" in text
    assert ("COPY --chown=medharness:medharness mcp/desensitize/key_provider/__init__.py") in text
    assert ("COPY --chown=medharness:medharness mcp/desensitize/key_provider/interface.py") in text
    assert (
        "COPY --chown=medharness:medharness mcp/desensitize/key_provider/file_provider.py"
    ) in text
    assert ("COPY --chown=medharness:medharness mcp/desensitize/sql/phi_lookup.sql") in text


def test_desensitize_dockerfile_excludes_skel_handoff_and_key_files() -> None:
    text = _dockerfile_text()

    assert ".skel" not in text
    assert "PROVIDER_HANDOFF.md" not in text
    assert "*.key" not in text
    assert not list(DESENSITIZE_DIR.rglob("*.key"))


def test_desensitize_dockerfile_entrypoint_serves_stdio() -> None:
    text = _dockerfile_text()

    assert 'ENTRYPOINT ["python", "server_v2.py"]' in text
    assert 'CMD ["serve", "--stdio"]' in text


def test_desensitize_requirements_are_per_mcp_slice() -> None:
    lines = [
        line.strip()
        for line in _requirements_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert lines == ["cryptography>=42.0,<46.0"]


def test_desensitize_does_not_include_dev_ml_or_key_deps() -> None:
    combined = f"{_dockerfile_text()}\n{_requirements_text()}".lower()

    forbidden = (
        "requirements-dev.txt",
        "pytest",
        "mkdocs",
        "ruff",
        "spacy",
        "presidio",
        "jieba",
        "zh_core_web_sm",
    )
    for marker in forbidden:
        assert marker not in combined


def test_desensitize_dockerfile_does_not_expose_secrets() -> None:
    text = _dockerfile_text().lower()

    forbidden = ("env ", "secret", "token", "password", "key=")
    for marker in forbidden:
        assert marker not in text
