from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "phi_fingerprint_check.py"
FIXTURES = [
    ROOT / "tests" / "red-team-drills" / "fixtures" / "synthetic_phi_corpus.jsonl",
    ROOT / "tests" / "red-team-drills" / "fixtures" / "synthetic_phi_negative_corpus.jsonl",
]


def _run_checker(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_t17_fixtures_pass_and_record_history(tmp_path: Path) -> None:
    history = tmp_path / "history.json"

    result = _run_checker("--history", history, *FIXTURES)

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert [file["lines"] for file in payload["files"]] == [220, 110]
    assert all(len(file["fingerprint"]) == 64 for file in payload["files"])

    history_payload = json.loads(history.read_text(encoding="utf-8"))
    assert len(history_payload) == 1
    assert history_payload[0]["files"][0]["lines"] == 220
    assert "text" not in json.dumps(history_payload, ensure_ascii=False).lower()


def test_missing_source_fails_validation(tmp_path: Path) -> None:
    fixture = tmp_path / "missing_source.jsonl"
    _write_jsonl(
        fixture,
        [{"id": "case-1", "text": "合成文本", "expected": [], "generator": "unit-test"}],
    )

    result = _run_checker("--history", tmp_path / "history.json", fixture)

    assert result.returncode == 1
    assert "source must be 'synthetic'" in result.stdout


def test_missing_generator_fails_validation(tmp_path: Path) -> None:
    fixture = tmp_path / "missing_generator.jsonl"
    _write_jsonl(
        fixture, [{"id": "case-1", "text": "合成文本", "expected": [], "source": "synthetic"}]
    )

    result = _run_checker("--history", tmp_path / "history.json", fixture)

    assert result.returncode == 1
    assert "generator metadata required" in result.stdout


def test_customer_marker_fails_validation(tmp_path: Path) -> None:
    fixture = tmp_path / "marker.jsonl"
    _write_jsonl(
        fixture,
        [
            {
                "id": "case-1",
                "text": "pacbio marker should be blocked",
                "expected": [],
                "source": "synthetic",
                "generator": "unit-test",
            }
        ],
    )

    result = _run_checker("--history", tmp_path / "history.json", fixture)

    assert result.returncode == 1
    assert "forbidden customer marker 'pacbio'" in result.stdout


def test_broken_jsonl_exits_parse_error(tmp_path: Path) -> None:
    fixture = tmp_path / "broken.jsonl"
    fixture.write_text('{"source": "synthetic", "generator": "unit-test"\n', encoding="utf-8")

    result = _run_checker("--history", tmp_path / "history.json", fixture)

    assert result.returncode == 2
    assert "invalid JSON" in result.stderr


def test_strict_mode_happy_path(tmp_path: Path) -> None:
    fixture = tmp_path / "strict.jsonl"
    _write_jsonl(
        fixture,
        [
            {
                "id": "case-1",
                "text": "合成文本",
                "expected": [],
                "source": "synthetic",
                "generator": "unit-test",
            }
        ],
    )

    result = _run_checker("--strict", "--history", tmp_path / "history.json", fixture)

    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["passed"] is True
