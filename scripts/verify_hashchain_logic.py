#!/usr/bin/env python3
"""T4.7 · verify hashchain on exported audit JSONL.

Exit codes:
  0 = chain intact
  1 = chain tampered or invalid
  2 = input file missing or unreadable
  3 = invalid JSONL format
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HASHCHAIN_DIR = ROOT / "mcp" / "audit-log"
sys.path.insert(0, str(HASHCHAIN_DIR))

from hashchain import verify_chain  # noqa: E402


def _load_rows(input_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with input_path.open(encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_num}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"invalid JSON on line {line_num}: expected object")
            rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify audit hashchain")
    parser.add_argument("--input", required=True, help="JSONL file with audit rows")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"error: input file not found: {input_path}", file=sys.stderr)
        return 2

    try:
        rows = _load_rows(input_path)
    except OSError as exc:
        print(f"error: failed to read input: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: failed to parse input: {exc}", file=sys.stderr)
        return 3

    if not rows:
        print(json.dumps({"status": "empty", "row_count": 0, "passed": True}))
        return 0

    ok, broken_at = verify_chain(rows)
    report = {
        "status": "ok" if ok else "tampered",
        "row_count": len(rows),
        "broken_at_row_id": broken_at,
        "passed": ok,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
