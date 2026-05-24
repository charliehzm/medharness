from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUB_NAMES = ("ci-trigger", "internal-kb", "pm-bridge", "vector-db")
STUB_MILESTONE = {
    "ci-trigger": "M4",
    "internal-kb": "M3",
    "pm-bridge": "M5",
    "vector-db": "M4",
}


def _dockerfile_text(stub: str) -> str:
    return (ROOT / "mcp" / stub / "Dockerfile").read_text(encoding="utf-8")


def _requirements_text(stub: str) -> str:
    return (ROOT / "mcp" / stub / "requirements.txt").read_text(encoding="utf-8")


def _requirement_lines(stub: str) -> list[str]:
    return [
        line.strip()
        for line in _requirements_text(stub).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_is_multi_stage_python_311_slim(stub: str) -> None:
    text = _dockerfile_text(stub)

    assert "ARG PYTHON_VERSION=3.11" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS builder" in text
    assert "FROM python:${PYTHON_VERSION}-slim AS runtime" in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_uses_non_root_medharness_user(stub: str) -> None:
    text = _dockerfile_text(stub)

    assert "groupadd --gid 9000 medharness" in text
    assert "useradd --uid 9000 --gid 9000" in text
    assert "USER medharness:medharness" in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_has_required_labels_and_args(stub: str) -> None:
    text = _dockerfile_text(stub)

    assert "ARG VERSION=unknown" in text
    assert "ARG GIT_COMMIT=unknown" in text
    assert f'org.opencontainers.image.title="medharness-{stub}"' in text
    assert "STUB · v0.5.0-edge placeholder" in text
    assert "org.opencontainers.image.version=$VERSION" in text
    assert "org.opencontainers.image.revision=$GIT_COMMIT" in text
    assert 'org.opencontainers.image.licenses="Apache-2.0"' in text
    assert 'org.opencontainers.image.source="https://github.com/charliehzm/medharness"' in text
    assert 'org.opencontainers.image.vendor="MedHarness"' in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_healthcheck_is_import_smoke(stub: str) -> None:
    text = _dockerfile_text(stub)

    assert "HEALTHCHECK" in text
    assert 'CMD python -c "import server" || exit 1' in text
    assert "python server.py health" not in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_copies_only_server_py_with_chown(stub: str) -> None:
    text = _dockerfile_text(stub)

    assert "WORKDIR /app" in text
    assert f"COPY --chown=medharness:medharness mcp/{stub}/server.py /app/server.py" in text
    assert f"COPY --chown=medharness:medharness mcp/{stub}/README.md" not in text
    assert f"COPY --chown=medharness:medharness mcp/{stub}/requirements.txt" not in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_entrypoint_serves_stdio(stub: str) -> None:
    text = _dockerfile_text(stub)

    assert 'ENTRYPOINT ["python", "server.py"]' in text
    assert 'CMD ["serve", "--stdio"]' in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_requirements_are_comment_only_with_milestone_note(stub: str) -> None:
    text = _requirements_text(stub)

    assert _requirement_lines(stub) == []
    assert "STUB v0.5.0-edge: intentionally empty" in text
    assert STUB_MILESTONE[stub] in text


@pytest.mark.parametrize("stub", STUB_NAMES)
def test_stub_dockerfile_and_requirements_exclude_heavy_and_dev_deps(stub: str) -> None:
    combined = f"{_dockerfile_text(stub)}\n{_requirements_text(stub)}".lower()
    forbidden = (
        "requirements-dev.txt",
        "pytest",
        "mkdocs",
        "ruff",
        "presidio",
        "cryptography",
        "clickhouse",
        "spacy",
        "jieba",
        "httpx",
    )

    for marker in forbidden:
        assert marker not in combined


def test_all_4_stubs_have_dockerfile_and_requirements() -> None:
    for stub in STUB_NAMES:
        assert (ROOT / "mcp" / stub / "Dockerfile").exists()
        assert (ROOT / "mcp" / stub / "requirements.txt").exists()
