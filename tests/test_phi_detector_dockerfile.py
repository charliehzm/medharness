from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "mcp" / "phi-detector" / "Dockerfile"
REQUIREMENTS = ROOT / "mcp" / "phi-detector" / "requirements.txt"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _requirements_text() -> str:
    return REQUIREMENTS.read_text(encoding="utf-8")


def test_phi_detector_dockerfile_is_multi_stage_python_311_slim() -> None:
    text = _dockerfile_text()

    assert "ARG PYTHON_VERSION=3.11" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS builder" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS runtime" in text


def test_phi_detector_dockerfile_uses_non_root_medharness_user() -> None:
    text = _dockerfile_text()

    assert "groupadd --gid 9000 medharness" in text
    assert "useradd --uid 9000 --gid 9000" in text
    assert "USER medharness:medharness" in text


def test_phi_detector_dockerfile_has_required_labels_and_args() -> None:
    text = _dockerfile_text()

    assert "ARG VERSION=unknown" in text
    assert "ARG GIT_COMMIT=unknown" in text
    assert "org.opencontainers.image.version=$VERSION" in text
    assert "org.opencontainers.image.revision=$GIT_COMMIT" in text
    assert 'org.opencontainers.image.licenses="Apache-2.0"' in text
    assert 'org.opencontainers.image.source="https://github.com/charliehzm/medharness"' in text


def test_phi_detector_dockerfile_healthcheck_calls_server_v3_health() -> None:
    text = _dockerfile_text()

    assert "HEALTHCHECK" in text
    assert "CMD python server_v3.py health || exit 1" in text


def test_phi_detector_dockerfile_copies_only_v3_runtime_files_with_chown() -> None:
    text = _dockerfile_text()

    assert "WORKDIR /app" in text
    assert "COPY --chown=medharness:medharness mcp/phi-detector/server_v3.py" in text
    assert "COPY --chown=medharness:medharness mcp/phi-detector/postprocess.py" in text
    assert "COPY --chown=medharness:medharness mcp/phi-detector/fields.yml" in text
    assert "COPY --chown=medharness:medharness mcp/phi-detector/recognizers/" in text
    assert "mcp/phi-detector/server.py" not in text
    assert "mcp/phi-detector/server_v2.py" not in text


def test_phi_detector_dockerfile_entrypoint_serves_stdio() -> None:
    text = _dockerfile_text()

    assert 'ENTRYPOINT ["python", "server_v3.py"]' in text
    assert 'CMD ["serve", "--stdio"]' in text


def test_phi_detector_requirements_are_per_mcp_slice() -> None:
    text = _requirements_text()

    assert "presidio-analyzer>=2.2,<3.0" in text
    assert "presidio-anonymizer>=2.2,<3.0" in text
    assert "spacy>=3.7,<4.0" in text
    assert "jieba>=0.42,<0.43" in text


def test_phi_detector_does_not_download_spacy_model_or_include_dev_deps() -> None:
    dockerfile = _dockerfile_text().lower()
    requirement_lines = [
        line.strip().lower()
        for line in _requirements_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    forbidden = (
        "python -m spacy download",
        "requirements-dev.txt",
        "pytest",
        "mkdocs",
        "ruff",
    )
    for marker in forbidden:
        assert marker not in dockerfile
        assert all(marker not in line for line in requirement_lines)
    assert all("zh_core_web_sm" not in line for line in requirement_lines)


def test_phi_detector_dockerfile_does_not_expose_secrets() -> None:
    text = _dockerfile_text().lower()

    forbidden = ("env ", "secret", "token", "password", "key=")
    for marker in forbidden:
        assert marker not in text
