#!/usr/bin/env python3
"""Validate synthetic PHI fixtures before they enter compliance drills.

Pre-commit hook integration point:

    python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl

The checker is intentionally offline-only. It validates JSONL fixture metadata,
blocks configured customer markers, compares canonical row hashes against a
forward-compatible known-real-PHI fingerprint blocklist, and records file-level
fingerprints without copying fixture text into the history artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_HISTORY = Path("tests/red-team-drills/output/phi_fingerprint_history.json")
EXIT_VALIDATION_FAILED = 1
EXIT_PARSE_OR_FILE_ERROR = 2

# v0.5.0 keeps this empty by design. If a real-PHI template is ever discovered,
# add only its SHA-256 fingerprint here, never the raw value.
KNOWN_REAL_PHI_FINGERPRINTS: set[str] = set()

DEFAULT_FORBIDDEN_MARKERS = (
    "pacbio",
    "huangzeming",
)


@dataclass(frozen=True)
class FixtureReport:
    path: str
    lines: int
    fingerprint: str
    passed: bool
    errors: list[str]


class ParseOrFileError(Exception):
    """Raised when a fixture cannot be read or parsed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def _forbidden_markers(extra: str | None = None) -> tuple[str, ...]:
    env_value = os.environ.get("MEDHARNESS_FORBIDDEN_MARKERS", "")
    markers = [*DEFAULT_FORBIDDEN_MARKERS]
    for source in (env_value, extra or ""):
        markers.extend(part.strip().lower() for part in source.split(",") if part.strip())
    return tuple(dict.fromkeys(markers))


def _iter_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_iter_values(item))
        return values
    if isinstance(value, list | tuple | set):
        values = []
        for item in value:
            values.extend(_iter_values(item))
        return values
    if value is None:
        return []
    return [str(value)]


def _blocked_fingerprints(row: dict[str, Any]) -> set[str]:
    row_and_value_hashes = {_sha256(_canonical_json(row))}
    row_and_value_hashes.update(_sha256(value) for value in _iter_values(row))
    return row_and_value_hashes & KNOWN_REAL_PHI_FINGERPRINTS


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseOrFileError(f"{path}: cannot read file: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParseOrFileError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ParseOrFileError(f"{path}:{line_no}: JSONL row must be an object")
        rows.append(row)
    return rows


def _file_fingerprint(rows: list[dict[str, Any]]) -> str:
    canonical_lines = sorted(_canonical_json(row) for row in rows)
    return _sha256("\n".join(canonical_lines) + "\n")


def validate_fixture(
    path: Path,
    *,
    strict: bool = False,
    forbidden_markers: tuple[str, ...] | None = None,
) -> FixtureReport:
    rows = _load_jsonl(path)
    markers = forbidden_markers if forbidden_markers is not None else _forbidden_markers()
    errors: list[str] = []

    for index, row in enumerate(rows, start=1):
        if row.get("source") != "synthetic":
            errors.append(f"{path}:{index}: source must be 'synthetic'")
        if not str(row.get("generator", "")).strip():
            errors.append(f"{path}:{index}: generator metadata required")

        if _blocked_fingerprints(row):
            errors.append(f"{path}:{index}: row fingerprint is blocked")

        lowered_values = [value.lower() for value in _iter_values(row)]
        for marker in markers:
            if any(marker in value for value in lowered_values):
                errors.append(f"{path}:{index}: forbidden customer marker '{marker}'")

        if strict:
            if "id" not in row:
                errors.append(f"{path}:{index}: id required in strict mode")
            if "expected" not in row or not isinstance(row.get("expected"), list):
                errors.append(f"{path}:{index}: expected list required in strict mode")
            text = row.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{path}:{index}: non-empty text required in strict mode")

    if strict and not rows:
        errors.append(f"{path}: at least one JSONL row required in strict mode")

    return FixtureReport(
        path=str(path),
        lines=len(rows),
        fingerprint=_file_fingerprint(rows),
        passed=not errors,
        errors=errors,
    )


def _append_history(history_path: Path, reports: list[FixtureReport]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if history_path.exists():
        try:
            existing = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
        if not isinstance(existing, list):
            existing = []
    else:
        existing = []

    existing.append(
        {
            "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "files": [
                {
                    "path": report.path,
                    "lines": report.lines,
                    "fingerprint": report.fingerprint,
                    "passed": report.passed,
                    "error_count": len(report.errors),
                }
                for report in reports
            ],
        }
    )
    history_path.write_text(
        json.dumps(existing[-100:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _report_payload(reports: list[FixtureReport], history_path: Path) -> dict[str, Any]:
    return {
        "checker": "phi_fingerprint_check",
        "schema_version": "T1.8",
        "passed": all(report.passed for report in reports),
        "history": str(history_path),
        "files": [
            {
                "path": report.path,
                "lines": report.lines,
                "fingerprint": report.fingerprint,
                "passed": report.passed,
                "errors": report.errors,
            }
            for report in reports
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", nargs="+", help="synthetic JSONL fixture path(s)")
    parser.add_argument("--strict", action="store_true", help="enforce full fixture row schema")
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
        help="fingerprint history JSON path",
    )
    parser.add_argument(
        "--forbidden-marker",
        default="",
        help="comma-separated customer markers, in addition to MEDHARNESS_FORBIDDEN_MARKERS",
    )
    args = parser.parse_args(argv)

    try:
        reports = [
            validate_fixture(
                Path(path),
                strict=args.strict,
                forbidden_markers=_forbidden_markers(args.forbidden_marker),
            )
            for path in args.jsonl
        ]
        _append_history(args.history, reports)
    except ParseOrFileError as exc:
        print(f"phi fingerprint check error: {exc}", file=sys.stderr)
        return EXIT_PARSE_OR_FILE_ERROR
    except OSError as exc:
        print(f"phi fingerprint check error: cannot write history: {exc}", file=sys.stderr)
        return EXIT_PARSE_OR_FILE_ERROR

    payload = _report_payload(reports, args.history)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else EXIT_VALIDATION_FAILED


if __name__ == "__main__":
    sys.exit(main())
