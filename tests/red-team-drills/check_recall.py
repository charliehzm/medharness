#!/usr/bin/env python3
"""CI gate: parse drill outputs and fail if recall below threshold."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=float, default=0.92)
    args = parser.parse_args()
    out_dir = Path(__file__).parent / "output"
    if not out_dir.exists():
        print("no drill output yet; run run_all.sh first", file=sys.stderr)
        return 2
    recall_file = out_dir / "recall.json"
    if not recall_file.exists():
        print("recall.json missing", file=sys.stderr)
        return 2
    data = json.loads(recall_file.read_text(encoding="utf-8"))
    ok = data.get("recall", 0) >= args.min
    print(
        json.dumps(
            {"recall": data.get("recall"), "min": args.min, "passed": ok}, ensure_ascii=False
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
