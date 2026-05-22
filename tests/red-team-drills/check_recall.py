#!/usr/bin/env python3
"""CI gate: enforce PHI recall drill output."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).parent / "output"
RECALL_FILE = OUT_DIR / "recall.json"
HISTORY_FILE = OUT_DIR / "recall_history.json"


def _load_recall_report() -> dict[str, Any]:
    if not OUT_DIR.exists():
        raise FileNotFoundError(f"{OUT_DIR} missing; run run_all.sh first")
    if not RECALL_FILE.exists():
        raise FileNotFoundError(f"{RECALL_FILE} missing; run drill_phi_recall.py first")
    try:
        data = json.loads(RECALL_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{RECALL_FILE} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{RECALL_FILE} must contain a JSON object")
    return data


def _number(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"{RECALL_FILE.name} missing numeric '{key}'")
    return float(value)


def _effective_recall(data: dict[str, Any]) -> float:
    recall = _number(data, "recall")
    detector_estimate = data.get("detector_recall_estimate")
    if isinstance(detector_estimate, int | float):
        return min(recall, float(detector_estimate))
    return recall


def _failure_reasons(data: dict[str, Any], min_recall: float, max_fp: float) -> list[str]:
    reasons: list[str] = []
    recall = _number(data, "recall")
    effective_recall = _effective_recall(data)
    if effective_recall < min_recall:
        reasons.append(f"effective recall {effective_recall:.4f} below required {min_recall:.4f}")
    fp_rate = data.get("false_positive_rate")
    if isinstance(fp_rate, int | float) and float(fp_rate) > max_fp:
        reasons.append(f"false_positive_rate {float(fp_rate):.4f} above allowed {max_fp:.4f}")
    failed_case_ids = data.get("failed_case_ids", [])
    if failed_case_ids:
        reasons.append(f"failed cases present: {failed_case_ids}")
    contract_violations = data.get("contract_violations", {})
    if contract_violations:
        reasons.append(f"contract violations present: {sorted(contract_violations)}")
    if data.get("passed") is False and recall >= min_recall and not failed_case_ids:
        reasons.append("drill marked report as failed")
    return reasons


def _append_history(data: dict[str, Any], min_recall: float, passed: bool) -> list[dict[str, Any]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
        if not isinstance(history, list):
            history = []
    else:
        history = []
    entry = {
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "schema_version": data.get("schema_version"),
        "cases": data.get("cases"),
        "expected_phi_mentions": data.get("expected_phi_mentions"),
        "recall": data.get("recall"),
        "effective_recall": round(_effective_recall(data), 4),
        "detector_recall_estimate": data.get("detector_recall_estimate"),
        "false_positive_rate": data.get("false_positive_rate"),
        "min": min_recall,
        "passed": passed,
        "failed_case_ids": data.get("failed_case_ids", []),
    }
    history.append(entry)
    HISTORY_FILE.write_text(
        json.dumps(history[-100:], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=float, default=0.92, help="min effective recall")
    parser.add_argument(
        "--max-fp", type=float, default=0.15, help="max false positive rate (default 0.15)"
    )
    args = parser.parse_args()
    try:
        data = _load_recall_report()
        reasons = _failure_reasons(data, args.min, args.max_fp)
    except (FileNotFoundError, ValueError) as exc:
        print(f"recall gate error: {exc}", file=sys.stderr)
        return 2

    passed = not reasons
    _append_history(data, args.min, passed)
    result = {
        "recall": data.get("recall"),
        "effective_recall": round(_effective_recall(data), 4),
        "detector_recall_estimate": data.get("detector_recall_estimate"),
        "false_positive_rate": data.get("false_positive_rate"),
        "min": args.min,
        "max_fp": args.max_fp,
        "passed": passed,
        "failed_case_ids": data.get("failed_case_ids", []),
        "reasons": reasons,
        "history": str(HISTORY_FILE),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
