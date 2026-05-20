#!/usr/bin/env python3
"""
mcp-vector-db · M4 占位实现
=============================
M1-M3：复用 internal-kb 的关键词检索（占位）。
M4 升级：真正接 Milvus + BGE-M3。

本文件保留接口契约，方法暂未实现 → 返回 not_implemented_yet。
"""

from __future__ import annotations

import json
import sys


def search(req: dict) -> dict:
    return {
        "status": "not_implemented_yet",
        "note": "M4 部署 Milvus + BGE-M3 后启用。当前可改用 mcp-internal-kb.search。",
        "fallback": "mcp/internal-kb/server.py search",
    }


def index_document(req: dict) -> dict:
    return {"status": "not_implemented_yet"}


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
        if method == "health":
            resp = {"id": req.get("id"), "result": {"status": "stub", "implements": ["M4-pending"]}}
        elif method == "search":
            resp = {"id": req.get("id"), "result": search(req.get("params", {}))}
        elif method == "index_document":
            resp = {"id": req.get("id"), "result": index_document(req.get("params", {}))}
        else:
            resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":
        print(json.dumps({"status": "stub", "implements": ["M4-pending"]}))
        return 0
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if cmd == "search":
        print(json.dumps(search(req), ensure_ascii=False))
        return 0
    if cmd == "index_document":
        print(json.dumps(index_document(req), ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
