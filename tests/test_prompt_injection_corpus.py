from __future__ import annotations

import json
import sys
from collections import Counter
from importlib import util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "tests" / "red-team-drills" / "fixtures" / "prompt_injection_corpus.jsonl"
DETECTOR_PATH = ROOT / "mcp" / "prompt-injection-scan" / "detector.py"

spec = util.spec_from_file_location("prompt_injection_detector_corpus", DETECTOR_PATH)
assert spec is not None
detector = util.module_from_spec(spec)
sys.modules["prompt_injection_detector_corpus"] = detector
assert spec.loader is not None
spec.loader.exec_module(detector)

REQUIRED_FIELDS = {"case_id", "attack_family", "text", "expected_block", "rationale"}
ATTACK_FAMILIES = set(detector.ALL_CATEGORIES)
BENIGN_FAMILY = "benign_control"
KNOWN_JAILBREAK_FINGERPRINTS = (
    "DAN 11.0",
    "Stan",
    "BetterDAN",
    "AIM Mode",
    "evil confidant",
    "jailbreakchat.com",
    "ChatGPT_DAN",
)


def _load_corpus() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with CORPUS_PATH.open(encoding="utf-8") as file:
        for line_num, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["_line_num"] = line_num
            cases.append(row)
    return cases


def test_corpus_file_exists_and_parseable() -> None:
    assert CORPUS_PATH.exists()
    assert _load_corpus()


def test_corpus_has_at_least_20_cases() -> None:
    assert len(_load_corpus()) >= 20


def test_corpus_covers_all_5_attack_families() -> None:
    counts = Counter(case["attack_family"] for case in _load_corpus())

    for family in ATTACK_FAMILIES:
        assert counts[family] >= 4
    assert counts[BENIGN_FAMILY] >= 3


def test_corpus_schema_completeness() -> None:
    for case in _load_corpus():
        missing = REQUIRED_FIELDS - set(case)
        assert not missing, f"case {case.get('case_id')} missing fields: {missing}"
        assert case["attack_family"] in ATTACK_FAMILIES | {BENIGN_FAMILY}
        assert isinstance(case["case_id"], str) and case["case_id"]
        assert isinstance(case["text"], str)
        assert isinstance(case["rationale"], str) and case["rationale"]
        assert len(case["text"]) < 200


def test_corpus_expected_block_values_are_boolean() -> None:
    for case in _load_corpus():
        assert isinstance(case["expected_block"], bool), case["case_id"]


def test_corpus_case_ids_are_unique() -> None:
    case_ids = [case["case_id"] for case in _load_corpus()]

    assert len(case_ids) == len(set(case_ids))


def test_corpus_no_real_jailbreak_library_fingerprint() -> None:
    text = CORPUS_PATH.read_text(encoding="utf-8")

    for fingerprint in KNOWN_JAILBREAK_FINGERPRINTS:
        assert fingerprint not in text, f"corpus contains real jailbreak fingerprint: {fingerprint}"


def test_corpus_sanity_block_rate_via_detector() -> None:
    cases = _load_corpus()
    expected_block_cases = [case for case in cases if case["expected_block"]]

    blocked = 0
    for case in expected_block_cases:
        context = {"data_source": "rag"} if "rag" in case["rationale"].lower() else None
        result = detector.detect_injection(case["text"], context)
        if result.blocked:
            blocked += 1

    block_rate = blocked / len(expected_block_cases)

    assert block_rate >= 0.90, f"corpus block rate {block_rate:.2%} below 90% sanity threshold"


def test_benign_controls_are_not_blocked_by_detector() -> None:
    benign_cases = [case for case in _load_corpus() if case["attack_family"] == BENIGN_FAMILY]

    for case in benign_cases:
        result = detector.detect_injection(case["text"])
        assert result.blocked is False, case["case_id"]
