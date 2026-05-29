#!/usr/bin/env python3
"""Red-team drill 5: read-API contract fixtures · PHI exfil scan.

The A0 read-only API is a new "PHI 出仓边界": Console renders gate internals to
humans for the first time. This drill walks every contract fixture and asserts
the return bodies contain 0 PHI and uphold the payload-null invariant for
security events.

Like the other drills, the report intentionally never copies raw fixture text
into artifacts — only file + JSON-path + entity label.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIX_DIR = ROOT / "web" / "src" / "api" / "contract" / "fixtures"

# 结构化 PHI 模式（保守，避免对聚合数/标签误报）
PHI_PATTERNS: dict[str, re.Pattern[str]] = {
    "cn_id": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "cn_phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "bank_card": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "cn_passport": re.compile(r"\b[EeGgDdSsPpHh]\d{8}\b"),
}
# 已知安全形式：纯哈希（hex ≥ 32）不算 PHI（如 sha256）
HEXISH = re.compile(r"^[0-9a-fA-F]{32,}$")
# 占位符形式 __NAME_a1__ —— 显式 0 PHI
PLACEHOLDER = re.compile(r"^__[A-Z]+_[a-z0-9]+__$")


def _iter_strings(node: Any, path: str) -> list[tuple[str, str]]:
    """递归收集 (json_path, value) 的所有字符串叶子。"""
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_iter_strings(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_iter_strings(v, f"{path}[{i}]"))
    elif isinstance(node, str):
        out.append((path, node))
    return out


def _scan_string(value: str) -> list[str]:
    """返回命中的 PHI 实体类型列表（不含原文）。"""
    if HEXISH.match(value):
        return []
    hits: list[str] = []
    for entity, pat in PHI_PATTERNS.items():
        for token in re.findall(r"\S+", value):
            if PLACEHOLDER.match(token):
                continue
            if pat.search(token):
                hits.append(entity)
                break
    return hits


def _payload_violations(node: Any, path: str) -> list[str]:
    """安全事件 / 告警的 payload 必须恒 null。"""
    out: list[str] = []
    if isinstance(node, dict):
        if "payload" in node and node["payload"] is not None:
            out.append(f"{path}.payload (expected null)")
        for k, v in node.items():
            out.extend(_payload_violations(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_payload_violations(v, f"{path}[{i}]"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not FIX_DIR.is_dir():
        out = {
            "drill": "api_phi_exfil",
            "passed": False,
            "error": f"contract fixtures dir not found: {FIX_DIR.relative_to(ROOT)}",
            "phi_hits": [],
            "payload_violations": [],
        }
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False))
        return 1

    files = sorted(FIX_DIR.glob("*.json"))
    strings_scanned = 0
    phi_hits: list[dict[str, str]] = []
    payload_violations: list[dict[str, str]] = []

    for fp in files:
        rel = str(fp.relative_to(ROOT))
        data = json.loads(fp.read_text(encoding="utf-8"))
        for jpath, value in _iter_strings(data, "$"):
            strings_scanned += 1
            for entity in _scan_string(value):
                phi_hits.append({"file": rel, "path": jpath, "entity": entity})
        for jpath in _payload_violations(data, "$"):
            payload_violations.append({"file": rel, "path": jpath})

    passed = not phi_hits and not payload_violations
    out = {
        "drill": "api_phi_exfil",
        "schema_version": "A0-0.6.0",
        "fixtures_scanned": len(files),
        "strings_scanned": strings_scanned,
        "phi_hits": phi_hits,
        "payload_violations": payload_violations,
        "passed": passed,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
