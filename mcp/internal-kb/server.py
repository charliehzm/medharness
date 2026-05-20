#!/usr/bin/env python3
"""
mcp-internal-kb · M3 起步实现
=================================
M3：关键词 + tf-idf 简易检索；M4 切真向量库。

数据来源：
  - .memory/项目档案.md
  - .memory/templates/*.md
  - openspec/templates/*.md
  - governance/*.md
  - openspec/changes/*/PRD_SUMMARY.md（archive 后通过 ingest 进入）
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PHI_DETECTOR_BIN = os.environ.get(
    "PHI_DETECTOR_BIN",
    str(Path(__file__).resolve().parent.parent / "phi-detector" / "server_v2.py"),
)

INJECTION_SCAN_PATTERNS = [
    re.compile(r"ignore (previous|all) instructions", re.I),
    re.compile(r"忽略.*指令"),
    re.compile(r"system prompt", re.I),
    re.compile(r"as your (admin|administrator|operator)", re.I),
    re.compile(r"<\|im_start\|>"),
]


def _project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _default_corpus() -> list[dict]:
    """加载默认 corpus（M3：从约定目录）。"""
    root = _project_root()
    docs = []
    for d in [".memory", "openspec/templates", "governance"]:
        base = root / d
        if not base.exists():
            continue
        for f in base.rglob("*.md"):
            try:
                docs.append(
                    {
                        "id": str(f.relative_to(root)),
                        "title": f.name,
                        "category": d.split("/")[0],
                        "text": f.read_text(encoding="utf-8"),
                    }
                )
            except Exception:
                continue
    return docs


def _tokenize(text: str) -> list[str]:
    # 极简：英数串 + 单 CJK
    return re.findall(r"[\w一-鿿]+", text.lower())


def _score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_counter = Counter(doc_tokens)
    score = 0.0
    for t in query_tokens:
        if doc_counter[t]:
            score += 1 + math.log(1 + doc_counter[t])
    return score / math.sqrt(len(doc_tokens))


def _injection_scan(text: str) -> str:
    for pat in INJECTION_SCAN_PATTERNS:
        if pat.search(text):
            return "quarantined"
    return "passed"


def _phi_scan(text: str) -> bool:
    """命中 = True（拒绝返回）。fail-closed。"""
    try:
        p = subprocess.run(
            ["python3", PHI_DETECTOR_BIN, "detect"],
            input=json.dumps({"text": text}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode != 0:
            return True
        r = json.loads(p.stdout)
        return bool(r.get("summary", {}).get("blocking_recommendation"))
    except Exception:
        return True


def search(query: str, k: int = 5, filter: dict | None = None) -> dict:
    docs = _default_corpus()
    qt = _tokenize(query)
    scored = []
    for d in docs:
        if filter and filter.get("category") and d["category"] != filter["category"]:
            continue
        score = _score(qt, _tokenize(d["text"]))
        if score <= 0:
            continue
        # 取最相关的一段
        para = max(d["text"].split("\n\n"), key=lambda p: _score(qt, _tokenize(p)), default="")
        snippet = para[:400]

        # 安全过滤
        if _phi_scan(snippet):
            continue  # 直接跳过；不返回 PHI hit
        inj = _injection_scan(snippet)
        if inj == "quarantined":
            continue
        scored.append(
            {
                "id": d["id"],
                "title": d["title"],
                "snippet": snippet,
                "source": d["id"],
                "confidence": round(score, 4),
                "injection_scan": inj,
            }
        )
    scored.sort(key=lambda x: -x["confidence"])
    return {"hits": scored[:k]}


def _serve_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method")
        params = req.get("params", {})
        if method == "search":
            result = search(params.get("query", ""), params.get("k", 5), params.get("filter"))
            resp = {"id": req.get("id"), "result": result}
        elif method == "health":
            resp = {
                "id": req.get("id"),
                "result": {"status": "ok", "corpus_size": len(_default_corpus())},
            }
        else:
            resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    if cmd == "health":
        print(json.dumps({"status": "ok", "corpus_size": len(_default_corpus())}))
        return 0
    if cmd == "search":
        req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        print(
            json.dumps(
                search(req.get("query", ""), req.get("k", 5), req.get("filter")), ensure_ascii=False
            )
        )
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
