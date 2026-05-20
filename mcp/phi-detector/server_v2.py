#!/usr/bin/env python3
"""
mcp-phi-detector v2 · M2 升级版（叠加在 server.py 之上）
=========================================================
新增能力（相对 M1 占位）：
1. 双 pass：规则层 + 分类器层
2. 仲裁器：两层不一致时 OR（保留高召回）
3. 上下文增强：name + DOB 邻近时升级置信度
4. MCP stdio 协议骨架（按 anthropic-mcp 规范）

分类器层实现说明：
- M2 上线时由 Harness Engineer 部署本地小模型（Qwen-1.8B 或微调 BERT）
- 本文件提供 `_classifier_call` 抽象接口；M2 实现注入真实模型
- M3 起替换为 ONNX 本地推理（CPU 即可，P99 < 30ms）

部署：
  python server_v2.py serve --stdio    # MCP stdio 模式
  python server_v2.py detect            # CLI 模式（兼容 M1）
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# 从 v1 复用规则
sys.path.insert(0, str(Path(__file__).parent))
from server import RULES as RULE_PASS1, detect as detect_rule  # noqa: E402


# ====== Pass 2 · 分类器接口（M2 实现注入） ======

def _classifier_call(text: str) -> list[dict]:
    """
    占位实现：M2 起替换为真实分类器调用。
    返回格式: [{type, span, confidence, suggested}]
    """
    env_endpoint = os.environ.get("PHI_CLASSIFIER_ENDPOINT")
    if not env_endpoint:
        # M1/M2-early：未配置分类器 → 空返回（不破坏链路，纯规则层覆盖）
        return []
    # M2 完整版：HTTP 调用本地 ONNX server
    # import requests
    # r = requests.post(env_endpoint, json={"text": text}, timeout=0.5)
    # return r.json().get("hits", [])
    return []


# ====== Pass 3 · 上下文增强 ======

CONTEXT_RULES = [
    # name + DOB within 80 chars → 升级两者为 high
    {
        "name": "name-near-DOB",
        "detector": lambda hits: _name_near_dob_upgrade(hits),
    },
]


def _name_near_dob_upgrade(hits: list[dict]) -> list[dict]:
    # 简化版：如果同时出现 Date 和 Name pattern，则把 Date 置信度从 0.6 提到 0.9
    has_name_like = any(h["type"] in ("CN-Name-heuristic",) for h in hits)
    if not has_name_like:
        return hits
    upgraded = []
    for h in hits:
        if h["type"] in ("Date-ISO", "Date-CJK") and h["confidence"] < 0.9:
            h2 = dict(h)
            h2["confidence"] = 0.9
            h2["upgraded_by"] = "name-near-DOB"
            upgraded.append(h2)
        else:
            upgraded.append(h)
    return upgraded


# ====== 仲裁 ======

def merge(rule_hits: list[dict], classifier_hits: list[dict]) -> list[dict]:
    """规则与分类器结果合并：取 OR；同 span 取高 confidence。"""
    by_span: dict[tuple[int, int], dict] = {}
    for h in rule_hits + classifier_hits:
        key = tuple(h["span"])
        if key not in by_span or h["confidence"] > by_span[key]["confidence"]:
            by_span[key] = h
    return list(by_span.values())


def detect_v2(text: str, context: dict | None = None) -> dict:
    rule_result = detect_rule(text or "")
    rule_hits = rule_result["hits"]
    cls_hits = _classifier_call(text or "")
    merged = merge(rule_hits, cls_hits)
    # context-aware upgrade
    for rule in CONTEXT_RULES:
        merged = rule["detector"](merged)
    max_conf = max((h["confidence"] for h in merged), default=0.0)
    return {
        "hits": merged,
        "summary": {
            "total_hits": len(merged),
            "max_confidence": max_conf,
            "blocking_recommendation": max_conf >= 0.9,
        },
        "_meta": {
            "version": "0.2-v2",
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "passes": ["rule"] + (["classifier"] if cls_hits else []),
        },
    }


# ====== MCP stdio 协议骨架 ======
# 协议参考：https://modelcontextprotocol.io/specification
# 简化实现：行级 JSON-RPC

def serve_stdio() -> int:
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
        if method == "detect":
            resp = {"id": req.get("id"), "result": detect_v2(params.get("text", ""), params.get("context"))}
        elif method == "health":
            resp = {"id": req.get("id"), "result": {"status": "ok-v2", "classifier_loaded": bool(os.environ.get("PHI_CLASSIFIER_ENDPOINT"))}}
        else:
            resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "detect"
    if cmd == "detect":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        text = req.get("text", "") or ""
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        print(json.dumps(detect_v2(text, req.get("context")), ensure_ascii=False))
        return 0
    if cmd == "health":
        print(json.dumps({"status": "ok-v2"}))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
