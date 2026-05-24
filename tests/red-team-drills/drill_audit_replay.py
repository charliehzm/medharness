#!/usr/bin/env python3
"""Red-team drill 3: audit replay hash-chain integrity checks.

All cases are synthetic JSONL chains. T4.9 verifies hash-chain integrity and
tamper detection only; semantic replay is deferred to T6/v0.6+.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERIFY_LOGIC = ROOT / "scripts" / "verify_hashchain_logic.py"
FIXTURE = Path(__file__).parent / "fixtures" / "audit_replay_bundle.jsonl"
SCHEMA_VERSION = "T4.audit_replay.v1"


def _run_verify(input_path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(VERIFY_LOGIC), "--input", str(input_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    report: dict[str, Any] = {
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    if proc.stdout.strip():
        try:
            report["verify_report"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            report["verify_report"] = None
    return report


def _load_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with FIXTURE.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _build_intact_case(fixture_path: Path) -> dict[str, Any]:
    verify = _run_verify(fixture_path)
    chain_intact = verify["exit_code"] == 0
    return {
        "case_id": "intact-chain",
        "vector": "full 6-month synthetic fixture",
        "expected_decision": "pass",
        "actual_decision": "pass" if chain_intact else "fail",
        "reason": "all rows verified" if chain_intact else verify.get("stderr", "verify failed"),
        "exit_code": verify["exit_code"],
        "row_count": verify.get("verify_report", {}).get("row_count"),
    }


def _build_tampered_mid_case(fixture_rows: list[dict[str, Any]], tmp_dir: Path) -> dict[str, Any]:
    tampered = [dict(row) for row in fixture_rows]
    mid = len(tampered) // 2
    tampered[mid]["result"] = {**tampered[mid]["result"], "status": "TAMPERED"}
    tampered_path = tmp_dir / "tampered_mid.jsonl"
    _write_jsonl(tampered_path, tampered)

    verify = _run_verify(tampered_path)
    tampered_detected = verify["exit_code"] == 1
    return {
        "case_id": "tampered-mid-row",
        "vector": f"row_id={mid} result.status mutated",
        "expected_decision": "fail",
        "actual_decision": "fail" if tampered_detected else "pass",
        "reason": (
            "tamper detected at expected row"
            if tampered_detected
            else "tamper NOT detected by hashchain verify"
        ),
        "exit_code": verify["exit_code"],
        "broken_at": verify.get("verify_report", {}).get("broken_at_row_id"),
    }


def _build_tampered_genesis_case(
    fixture_rows: list[dict[str, Any]], tmp_dir: Path
) -> dict[str, Any]:
    tampered = [dict(row) for row in fixture_rows]
    tampered[0]["prev_hash"] = "not-genesis"
    tampered_path = tmp_dir / "tampered_genesis.jsonl"
    _write_jsonl(tampered_path, tampered)

    verify = _run_verify(tampered_path)
    tampered_detected = verify["exit_code"] == 1
    return {
        "case_id": "tampered-genesis",
        "vector": "row 0 prev_hash mutated from GENESIS",
        "expected_decision": "fail",
        "actual_decision": "fail" if tampered_detected else "pass",
        "reason": "genesis tamper detected" if tampered_detected else "genesis tamper NOT detected",
        "exit_code": verify["exit_code"],
        "broken_at": verify.get("verify_report", {}).get("broken_at_row_id"),
    }


def _build_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [case["case_id"] for case in cases if case["actual_decision"] != case["expected_decision"]]
    intact = next((case for case in cases if case["case_id"] == "intact-chain"), None)
    tampered_cases = [case for case in cases if case["case_id"].startswith("tampered-")]
    return {
        "schema_version": SCHEMA_VERSION,
        "drill": "audit_replay",
        "total_cases": len(cases),
        "chain_intact": bool(intact and intact["actual_decision"] == "pass"),
        "tampered_detected": all(case["actual_decision"] == "fail" for case in tampered_cases),
        "passed": not failed,
        "failed_case_ids": failed,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    fixture_rows = _load_fixture()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cases = [
            _build_intact_case(FIXTURE),
            _build_tampered_mid_case(fixture_rows, tmp_dir),
            _build_tampered_genesis_case(fixture_rows, tmp_dir),
        ]

    report = _build_report(cases)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
