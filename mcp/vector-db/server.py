#!/usr/bin/env python3
"""
mcp-vector-db · community-edition 实现（本地内存向量库）
======================================================
社区版定位：**单机 / 内存 / 0 外部依赖 / 0 模型下载**。

向量化不走 BGE-M3 等需下载的大模型，而是用**字符 3-gram 哈希向量器**
(hashing vectorizer)：把文本切成 3-gram，按 hash 落到固定维 (DIM=256)
的桶里，再 L2 归一化得到稠密向量。纯 stdlib (`math` + `hashlib`)，
确定性可复现，足以支撑社区版 demo 的"真实向量检索"。

接口契约（与 internal-kb 对齐）：
  - index_document({id, text, metadata?}) -> {indexed, id, dim}
  - search({query, k=5, filter?})         -> {hits:[{id,score,text,metadata}], count}
  - health()                               -> {status:"ok", vectors, dim}

安全纪律（镜像 internal-kb）：
  - 返回 snippet 前做 PHI 扫描（fail-closed）+ prompt-injection 扫描；
  - 命中即跳过该 hit，绝不把 PHI / 注入内容回流到上下文；
  - snippet 长度封顶 SNIPPET_MAX。

企业版（非社区）才接 Milvus + BGE-M3；本文件不依赖之。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

DIM = 256
NGRAM = 3
SNIPPET_MAX = 400

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

# In-memory store: {id: {"vector": list[float], "text": str, "metadata": dict}}
_STORE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# 向量化（字符 n-gram 哈希向量器，纯 stdlib）
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    # 折叠空白、统一小写；保留 CJK
    return re.sub(r"\s+", " ", text.lower()).strip()


def _ngrams(text: str, n: int = NGRAM) -> list[str]:
    text = _normalize(text)
    if not text:
        return []
    if len(text) < n:
        return [text]
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def _embed(text: str, dim: int = DIM) -> list[float]:
    """字符 n-gram → 固定维稠密向量 → L2 归一化。确定性。"""
    vec = [0.0] * dim
    for gram in _ngrams(text):
        h = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        # 用第 5 字节最低位决定 ±，降低哈希碰撞带来的系统性偏置
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    # 两向量均已 L2 归一化 → 点积即 cosine
    return sum(x * y for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------------------
# 安全过滤（镜像 internal-kb）
# ---------------------------------------------------------------------------
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


def _snippet(text: str) -> str:
    return text[:SNIPPET_MAX]


# ---------------------------------------------------------------------------
# 默认合成语料（SYNTHETIC · 0 PHI · 0 患者标识）
# ---------------------------------------------------------------------------
_SEED_CORPUS: list[dict] = [
    {
        "id": "seed-hipaa-minimum-necessary",
        "text": (
            "最小必要原则：仅在完成既定用途所需的最小范围内访问、使用与共享受保护健康信息。"
            " The HIPAA minimum necessary standard limits PHI access to the least amount required."
        ),
        "metadata": {"category": "compliance", "framework": "HIPAA", "synthetic": True},
    },
    {
        "id": "seed-pipl-cross-border",
        "text": (
            "个人信息保护法要求跨境传输健康数据前完成安全评估与单独同意。"
            " PIPL mandates a security assessment and separate consent before cross-border health data transfer."
        ),
        "metadata": {"category": "compliance", "framework": "PIPL", "synthetic": True},
    },
    {
        "id": "seed-deidentification",
        "text": (
            "去标识化将直接标识符替换为合成占位符，使数据无法重新关联到自然人。"
            " De-identification replaces direct identifiers with synthetic placeholders so records cannot be re-linked."
        ),
        "metadata": {"category": "governance", "topic": "de-identification", "synthetic": True},
    },
    {
        "id": "seed-audit-trail",
        "text": (
            "审计留痕要求对每次模型与工具调用全量记录，保留期满足六年可回放要求。"
            " Audit trails record every model and tool call with six-year replayability."
        ),
        "metadata": {"category": "governance", "topic": "audit", "synthetic": True},
    },
    {
        "id": "seed-data-tiering",
        "text": (
            "数据分级 L1 到 L4：L4 为含直接患者标识的最高敏感级，永不裸入提示词。"
            " Data tiers L1-L4: L4 holds direct patient identifiers and never enters a prompt raw."
        ),
        "metadata": {"category": "governance", "topic": "data-tiering", "synthetic": True},
    },
]


def _seed_store() -> None:
    """启动时灌入合成语料，使开箱即用的 search 有返回。幂等。"""
    for doc in _SEED_CORPUS:
        if doc["id"] in _STORE:
            continue
        _STORE[doc["id"]] = {
            "vector": _embed(doc["text"]),
            "text": doc["text"],
            "metadata": dict(doc.get("metadata", {})),
        }


# ---------------------------------------------------------------------------
# 公开方法
# ---------------------------------------------------------------------------
def index_document(req: dict) -> dict:
    doc_id = req.get("id")
    text = req.get("text", "")
    if not doc_id:
        return {"indexed": False, "error": "missing id"}
    if not isinstance(text, str) or not text.strip():
        return {"indexed": False, "id": doc_id, "error": "empty text"}
    metadata = req.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    _STORE[doc_id] = {
        "vector": _embed(text),
        "text": text,
        "metadata": metadata,
    }
    return {"indexed": True, "id": doc_id, "dim": DIM}


def search(req: dict) -> dict:
    query = req.get("query", "")
    k = req.get("k", 5)
    filter = req.get("filter")
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 5
    k = max(0, k)

    if not isinstance(query, str) or not query.strip() or not _STORE:
        return {"hits": [], "count": 0}

    qvec = _embed(query)
    scored = []
    for doc_id, rec in _STORE.items():
        if filter and isinstance(filter, dict):
            meta = rec.get("metadata", {})
            if any(meta.get(fk) != fv for fk, fv in filter.items()):
                continue
        score = _cosine(qvec, rec["vector"])
        if score <= 0:
            continue
        snippet = _snippet(rec["text"])
        # 安全过滤：PHI（fail-closed）→ 注入；命中即跳过
        if _phi_scan(snippet):
            continue
        if _injection_scan(snippet) == "quarantined":
            continue
        scored.append(
            {
                "id": doc_id,
                "score": round(score, 4),
                "text": snippet,
                "metadata": rec.get("metadata", {}),
            }
        )
    scored.sort(key=lambda x: -x["score"])
    hits = scored[:k]
    return {"hits": hits, "count": len(hits)}


def health() -> dict:
    return {"status": "ok", "vectors": len(_STORE), "dim": DIM}


# 模块导入即灌种子语料（保证 `import server` healthcheck 不受影响 / 开箱有数据）
_seed_store()


# ---------------------------------------------------------------------------
# serve 模式
# ---------------------------------------------------------------------------
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
        try:
            if method == "health":
                result = health()
            elif method == "search":
                result = search(params)
            elif method == "index_document":
                result = index_document(params)
            else:
                resp = {
                    "id": req.get("id"),
                    "error": {"code": -32601, "message": "Method not found"},
                }
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                continue
            resp = {"id": req.get("id"), "result": result}
        except Exception as e:
            resp = {"id": req.get("id"), "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def _serve_http(host: str, port: int) -> int:
    """Long-lived HTTP health endpoint so this service stays up in a detached
    container — the default `serve --stdio` hits stdin EOF and exits, which
    restart-loops under compose. Only GET /health is served (compose healthcheck)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path.rstrip("/") in ("", "/health"):
                payload = {"service": "vector-db", **health()}
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    ThreadingHTTPServer((host, port), _Handler).serve_forever()
    return 0


def main() -> int:
    if sys.argv[1:3] == ["serve", "--http"]:
        host, port = "0.0.0.0", 9000
        rest = sys.argv[3:]
        for i, a in enumerate(rest):
            if a == "--host" and i + 1 < len(rest):
                host = rest[i + 1]
            elif a == "--port" and i + 1 < len(rest):
                port = int(rest[i + 1])
        return _serve_http(host, port)
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":
        print(json.dumps(health()))
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
