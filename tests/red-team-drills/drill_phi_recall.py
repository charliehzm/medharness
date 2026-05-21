#!/usr/bin/env python3
"""Red-team drill 1: PHI detection recall on synthetic corpus.

The drill consumes the v0.5 detector envelope (`spans` + `stats`) while
accepting legacy `hits` during the T1 migration window. Reports intentionally
avoid copying raw fixture text into artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "red-team-drills" / "fixtures" / "synthetic_phi_corpus.jsonl"
MIN_RECALL = 0.92
ENTITY_ALIASES = {
    "cn-id": "cn_id",
    "cn_id": "cn_id",
    "cn-phone": "cn_phone",
    "cn_phone": "cn_phone",
    "cn-mrn": "cn_mrn",
    "cn_mrn": "cn_mrn",
    "cn-bank": "cn_bank",
    "cn_bank": "cn_bank",
    "cn-passport": "cn_passport",
    "cn_passport": "cn_passport",
    "cn-hk-id": "cn_hk_id",
    "cn_hk_id": "cn_hk_id",
    "cn-drivers-license": "cn_drivers_license",
    "cn_drivers_license": "cn_drivers_license",
    "cn-address": "cn_address",
    "cn_address": "cn_address",
    "cn-disease-code": "cn_disease_code",
    "cn_disease_code": "cn_disease_code",
    "cn-drug-code": "cn_drug_code",
    "cn_drug_code": "cn_drug_code",
}
BASELINE_CASES = [
    {
        "id": "baseline-cn-id",
        "text": "合成患者证件号 110101199001011237 已核验",
        "expected": ["cn_id"],
    },
    {
        "id": "baseline-cn-phone",
        "text": "合成随访手机号 13912345678",
        "expected": ["cn_phone"],
    },
    {
        "id": "baseline-cn-mrn",
        "text": "合成病历号 AB12345678",
        "expected": ["cn_mrn"],
    },
    {
        "id": "baseline-negative",
        "text": "合成天气说明，不包含可识别字段",
        "expected": [],
    },
]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    expected: set[str]
    detected: set[str]
    false_positive: set[str]
    missing: set[str]
    contract_violations: list[str]
    detector_recall_estimate: float | None


def _ensure_fixture() -> None:
    if FIXTURE.exists():
        return
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in BASELINE_CASES),
        encoding="utf-8",
    )


def _load_cases() -> list[dict[str, Any]]:
    _ensure_fixture()
    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(FIXTURE.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        case.setdefault("id", f"line-{line_no}")
        case.setdefault("expected", [])
        cases.append(case)
    return cases


def _detect_phi(text: str) -> dict[str, Any]:
    phi_dir = ROOT / "mcp" / "phi-detector"
    if str(phi_dir) not in sys.path:
        sys.path.insert(0, str(phi_dir))
    import server_v3  # noqa: PLC0415

    result = server_v3.detect_v3(text)
    if isinstance(result, dict):
        return result
    return {"hits": result, "stats": {}}


def _normalize_entity(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    return ENTITY_ALIASES.get(raw, raw)


def _normalize_spans(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_spans = response.get("spans")
    if raw_spans is None:
        raw_spans = response.get("hits", [])
    if not isinstance(raw_spans, list):
        return []
    normalized: list[dict[str, Any]] = []
    for span in raw_spans:
        if not isinstance(span, dict):
            continue
        start = span.get("start")
        end = span.get("end")
        legacy_span = span.get("span")
        if (
            (start is None or end is None)
            and isinstance(legacy_span, list | tuple)
            and len(legacy_span) == 2
        ):
            start, end = legacy_span
        entity = span.get("entity_type", span.get("type"))
        normalized.append(
            {
                "entity": _normalize_entity(entity),
                "start": start,
                "end": end,
                "score": span.get("score", span.get("confidence")),
                "text_sha256": span.get("text_sha256"),
            }
        )
    return normalized


def _contract_violations(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    text = str(case.get("text", ""))
    violations: list[str] = []
    raw_spans = response.get("spans", response.get("hits", []))
    if not isinstance(raw_spans, list):
        raw_spans = []
    for span in raw_spans:
        if not isinstance(span, dict):
            continue
        if "text" in span or "match" in span or "matched_text" in span:
            violations.append("span contains raw text field")
        start = span.get("start")
        end = span.get("end")
        legacy_span = span.get("span")
        if (
            (start is None or end is None)
            and isinstance(legacy_span, list | tuple)
            and len(legacy_span) == 2
        ):
            start, end = legacy_span
        if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text):
            matched = text[start:end]
            if matched and matched in json.dumps(response, ensure_ascii=False):
                violations.append("response contains raw matched text")
    serialized = json.dumps(response, ensure_ascii=False)
    for expected in _expected_values(case):
        if expected and expected in serialized:
            violations.append("response contains raw expected value")
    if text and text in serialized:
        violations.append("response contains raw case text")
    return sorted(set(violations))


def _expected_values(case: dict[str, Any]) -> list[str]:
    values = case.get("expected_values", [])
    if isinstance(values, list):
        return [str(value) for value in values if value]
    return []


def _evaluate_case(case: dict[str, Any]) -> CaseResult:
    expected = {_normalize_entity(entity) for entity in case.get("expected", [])}
    response = _detect_phi(str(case.get("text", "")))
    spans = _normalize_spans(response)
    detected = {span["entity"] for span in spans if span["entity"]}
    false_positive = detected - expected
    missing = expected - detected
    stats = response.get("stats", {})
    recall_estimate = stats.get("recall_estimate") if isinstance(stats, dict) else None
    return CaseResult(
        case_id=str(case["id"]),
        expected=expected,
        detected=detected,
        false_positive=false_positive,
        missing=missing,
        contract_violations=_contract_violations(case, response),
        detector_recall_estimate=recall_estimate
        if isinstance(recall_estimate, int | float)
        else None,
    )


def _entity_coverage(results: list[CaseResult]) -> dict[str, dict[str, int | float]]:
    entities = sorted({entity for result in results for entity in result.expected})
    coverage: dict[str, dict[str, int | float]] = {}
    for entity in entities:
        expected = sum(1 for result in results if entity in result.expected)
        detected = sum(1 for result in results if entity in result.expected & result.detected)
        coverage[entity] = {
            "expected": expected,
            "detected": detected,
            "recall": round(detected / expected, 4) if expected else 1.0,
        }
    return coverage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    cases = _load_cases()
    results = [_evaluate_case(case) for case in cases]
    total_expected = sum(len(result.expected) for result in results)
    total_detected = sum(len(result.expected & result.detected) for result in results)
    false_positive_cases = [result.case_id for result in results if result.false_positive]
    failed_case_ids = [
        result.case_id
        for result in results
        if result.missing or result.false_positive or result.contract_violations
    ]
    contract_violations = {
        result.case_id: result.contract_violations
        for result in results
        if result.contract_violations
    }
    recall = (total_detected / total_expected) if total_expected else 1.0
    fp_rate = (len(false_positive_cases) / len(results)) if results else 0.0
    out = {
        "drill": "phi_recall",
        "schema_version": "T1.6",
        "cases": len(cases),
        "expected_phi_mentions": total_expected,
        "detected": total_detected,
        "recall": round(recall, 4),
        "false_positive_rate": round(fp_rate, 4),
        "per_entity_coverage": _entity_coverage(results),
        "failed_case_ids": failed_case_ids,
        "false_positive_case_ids": false_positive_cases,
        "contract_violations": contract_violations,
        "detector_recall_estimate": _detector_recall_estimate(results),
        "min_required": MIN_RECALL,
        "passed": recall >= MIN_RECALL and not failed_case_ids,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["passed"] else 1


def _detector_recall_estimate(results: list[CaseResult]) -> float | None:
    estimates = [
        result.detector_recall_estimate
        for result in results
        if result.expected and result.detector_recall_estimate is not None
    ]
    if not estimates:
        return None
    return round(max(estimates), 4)


if __name__ == "__main__":
    sys.exit(main())
