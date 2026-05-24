from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from importlib import util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DRILL_PATH = ROOT / "tests" / "red-team-drills" / "drill_injection.py"
CORPUS_PATH = ROOT / "tests" / "red-team-drills" / "fixtures" / "prompt_injection_corpus.jsonl"
DETECTOR_PATH = ROOT / "mcp" / "prompt-injection-scan" / "detector.py"

drill_spec = util.spec_from_file_location("prompt_injection_drill_test", DRILL_PATH)
assert drill_spec is not None
drill = util.module_from_spec(drill_spec)
sys.modules["prompt_injection_drill_test"] = drill
assert drill_spec.loader is not None
drill_spec.loader.exec_module(drill)

detector_spec = util.spec_from_file_location("prompt_injection_detector_test", DETECTOR_PATH)
assert detector_spec is not None
detector = util.module_from_spec(detector_spec)
sys.modules["prompt_injection_detector_test"] = detector
assert detector_spec.loader is not None
detector_spec.loader.exec_module(detector)

RAW_SENTINEL = "RAW-PHI-CLAIM"


def _load_corpus() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_drill_classifies_true_positive() -> None:
    assert drill._classify(True, True) == "true_positive"


def test_drill_classifies_false_negative_marks_failed() -> None:
    assert drill._classify(True, False) == "false_negative"


def test_drill_classifies_false_positive_marks_failed() -> None:
    assert drill._classify(False, True) == "false_positive"


def test_drill_classifies_true_negative() -> None:
    assert drill._classify(False, False) == "true_negative"


def test_drill_block_rate_calculation() -> None:
    report = drill._aggregate(
        [
            {
                "case_id": "a",
                "attack_family": "indirect_injection",
                "expected_block": True,
                "actual_block": True,
                "category": "indirect_injection",
                "score": 0.7,
                "matched_rules": ["x"],
                "outcome": "true_positive",
            },
            {
                "case_id": "b",
                "attack_family": "indirect_injection",
                "expected_block": True,
                "actual_block": False,
                "category": None,
                "score": 0.0,
                "matched_rules": [],
                "outcome": "false_negative",
            },
        ]
    )

    assert report["block_rate"] == 0.5
    assert report["false_negatives"] == 1
    assert report["failed_case_ids"] == ["b"]


def test_drill_fp_rate_calculation() -> None:
    report = drill._aggregate(
        [
            {
                "case_id": "a",
                "attack_family": "benign_control",
                "expected_block": False,
                "actual_block": True,
                "category": "tool_abuse",
                "score": 0.6,
                "matched_rules": ["tool_shell_exec"],
                "outcome": "false_positive",
            },
            {
                "case_id": "b",
                "attack_family": "benign_control",
                "expected_block": False,
                "actual_block": False,
                "category": None,
                "score": 0.0,
                "matched_rules": [],
                "outcome": "true_negative",
            },
        ]
    )

    assert report["fp_rate"] == 0.5
    assert report["false_positives"] == 1
    assert report["failed_case_ids"] == ["a"]


def test_drill_passes_when_all_correct_and_block_rate_above_threshold(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(DRILL_PATH), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    report = _load_report(out)

    assert proc.returncode == 0
    assert report["passed"] is True
    assert report["block_rate"] >= 0.95
    assert report["fp_rate"] == 0.0


def test_drill_fails_when_block_rate_below_95_percent(tmp_path: Path) -> None:
    del tmp_path
    report = drill._aggregate(
        [
            {
                "case_id": "tp",
                "attack_family": "indirect_injection",
                "expected_block": True,
                "actual_block": True,
                "category": "indirect_injection",
                "score": 0.7,
                "matched_rules": ["indirect_ignore_instructions"],
                "outcome": "true_positive",
                "rationale": "synthetic",
            },
            {
                "case_id": "fn",
                "attack_family": "indirect_injection",
                "expected_block": True,
                "actual_block": False,
                "category": None,
                "score": 0.0,
                "matched_rules": [],
                "outcome": "false_negative",
                "rationale": "synthetic",
            },
        ]
    )

    assert report["passed"] is False
    assert report["block_rate"] < 0.95
    assert report["failed_case_ids"] == ["fn"]


def test_drill_report_includes_per_family_stats(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    subprocess.run(
        [sys.executable, str(DRILL_PATH), "--out", str(out)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    report = _load_report(out)
    counts = Counter(case["attack_family"] for case in _load_corpus())

    assert set(report["per_family"]) == set(counts)
    for family, stats in report["per_family"].items():
        assert stats["total"] == counts[family]
        assert stats["blocked"] <= stats["total"]
        assert stats["expected_block"] <= stats["total"]


def test_drill_report_does_not_leak_case_text_in_reason(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    subprocess.run(
        [sys.executable, str(DRILL_PATH), "--out", str(out)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    report = _load_report(out)

    report_text = json.dumps(report, ensure_ascii=False)
    assert RAW_SENTINEL not in report_text
    assert "prompt_injection_corpus" not in report_text
    for case in _load_corpus():
        assert case["text"] not in report_text


def test_drill_run_against_real_corpus_passes(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(DRILL_PATH), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    report = _load_report(out)

    assert proc.returncode == 0
    assert report["passed"] is True
    assert report["block_rate"] == 1.0
    assert report["fp_rate"] == 0.0
    assert report["failed_case_ids"] == []


def test_drill_does_not_log_case_text_to_stdout_or_stderr(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(DRILL_PATH), "--out", str(out)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert RAW_SENTINEL not in proc.stdout
    assert RAW_SENTINEL not in proc.stderr
    for case in _load_corpus():
        assert case["text"] not in proc.stdout
        assert case["text"] not in proc.stderr
