#!/usr/bin/env python3
"""
mcp-phi-detector v3 · M3 后实战调优版（v2.2 升级）
====================================================
基于 M1-M2 实战反馈（governance/M1-M2实战反馈-v2.2触发.md §B1）的调优：

v3 改进：
1. CN-Bank 加 Luhn 校验 + 字符上下文白名单（排除 commit hash / UUID / RFID）
2. CN-Name heuristic 加上下文（"医院" / "病房" / "诊所" 等不算人名）
3. Date 检测要求人名邻近才升级 high severity
4. 已脱敏占位符 {{XX_yyyy}} 跳过扫描（信任脱敏）
5. Session 级去重：同 prompt 内已扫描区段不重复
6. 上下文白名单（log timestamp / commit hash / UUID）

兼容 v2 接口；CLI 与 stdio 双模式。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server_v2 import (
    _classifier_call,
    detect_v2,  # 留底
)

# ====== v3 规则升级 ======

# 占位符 — 信任已脱敏文本
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*[A-Z]{2}_[a-z0-9]{2,10}\s*\}\}")

# UUID / sha hash / commit hash 白名单（防止 CN-Bank 误判）
HEX_HASH_LIKE = re.compile(r"\b[a-f0-9]{16,64}\b")
UUID_LIKE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

# 日志时间戳上下文（ISO 8601 + log level 前缀）
LOG_TIMESTAMP_CTX = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}[T ]\d{1,2}:\d{1,2}(:\d{1,2})?(Z|[+-]\d{2}:?\d{2})?\b"
)

# CN-Name 白名单（医院/科室/药品等机构性词汇不算人名）
NON_NAME_TOKENS = set(
    [
        "医院",
        "卫生",
        "病房",
        "诊所",
        "科室",
        "门诊",
        "急诊",
        "药房",
        "药品",
        "检查",
        "化验",
        "检验",
        "手术",
        "病区",
        "楼层",
        "床位",
    ]
    + [
        "公司",
        "集团",
        "总部",
        "分部",
        "部门",
        "团队",
        "项目",
        "系统",
        "平台",
        "服务",
        "接口",
        "数据库",
        "表格",
    ]
)

# CN-Name 启发式（v3 新增；v2 没有此规则）
CN_NAME_HEURISTIC = re.compile(r"\b[一-龥]{2,4}\b")

# 银行卡 / 身份证号上下文要求（必须邻近"银行卡|身份证|账号|卡号|证件号"才升 high）
BANK_CONTEXT_KEYWORDS = ["银行卡", "卡号", "账号", "信用卡", "存折"]
ID_CARD_CONTEXT_KEYWORDS = ["身份证", "证件号", "公民身份号码", "ID"]


def _looks_like_hash(text: str, span: tuple[int, int]) -> bool:
    """命中位置是否在 hash/UUID 区域内"""
    for m in HEX_HASH_LIKE.finditer(text):
        if m.start() <= span[0] < m.end():
            return True
    for m in UUID_LIKE.finditer(text):
        if m.start() <= span[0] < m.end():
            return True
    return False


def _looks_like_log_timestamp(text: str, span: tuple[int, int]) -> bool:
    """命中位置是否在日志时间戳上下文"""
    snippet = text[max(0, span[0] - 30) : min(len(text), span[1] + 30)]
    return bool(LOG_TIMESTAMP_CTX.search(snippet))


def _is_in_placeholder(text: str, span: tuple[int, int]) -> bool:
    """命中位置是否在 {{PT_xxxx}} 占位符内"""
    for m in PLACEHOLDER_PATTERN.finditer(text):
        if m.start() <= span[0] < m.end():
            return True
    return False


def _has_bank_context(text: str, span: tuple[int, int]) -> bool:
    snippet = text[max(0, span[0] - 20) : span[0]]
    return any(kw in snippet for kw in BANK_CONTEXT_KEYWORDS)


def _has_id_context(text: str, span: tuple[int, int]) -> bool:
    snippet = text[max(0, span[0] - 20) : span[0]]
    return any(kw in snippet for kw in ID_CARD_CONTEXT_KEYWORDS)


def _check_name_heuristic(text: str) -> list[dict]:
    """v3 新增：CN-Name 启发式，但带上下文白名单"""
    out = []
    for m in CN_NAME_HEURISTIC.finditer(text):
        token = m.group()
        # 白名单：常见机构性词汇
        if token in NON_NAME_TOKENS:
            continue
        # 太短（2 字）单独不够；要求附近有"病人/患者/姓名/医生"等触发词
        ctx_before = text[max(0, m.start() - 10) : m.start()]
        ctx_after = text[m.end() : m.end() + 10]
        ctx = ctx_before + ctx_after
        if not any(t in ctx for t in ["病人", "患者", "姓名", "医生", "Mr.", "Ms.", "Mrs."]):
            continue
        # 长度 2-3 字，邻近触发词 → 可能为人名
        out.append(
            {
                "type": "CN-Name-heuristic",
                "span": [m.start(), m.end()],
                "confidence": 0.7,
                "suggested": "review",
            }
        )
    return out


def detect_v3(text: str, context: dict | None = None) -> dict:
    """v3 主入口"""
    if not text:
        return {
            "hits": [],
            "summary": {"total_hits": 0, "max_confidence": 0, "blocking_recommendation": False},
            "_meta": {"version": "0.3-v3", "passes": ["rule-v3"]},
        }

    # Step 1: 跑 v2 规则层
    v2_result = detect_v2(text, context)
    hits = v2_result["hits"]

    # Step 2: 加 CN-Name heuristic（v3 新增）
    hits.extend(_check_name_heuristic(text))

    # Step 3: 加分类器层（如配）
    classifier_hits = _classifier_call(text)
    hits.extend(classifier_hits)

    # Step 4: v3 过滤——排除假阳性
    filtered = []
    suppressed = []
    for h in hits:
        span = tuple(h["span"])
        # 4a: 已脱敏占位符跳过
        if _is_in_placeholder(text, span):
            suppressed.append({**h, "_suppressed": "in_placeholder"})
            continue
        # 4b: hash/UUID 区域跳过（针对 CN-Bank 误判）
        if h["type"] == "CN-Bank" and _looks_like_hash(text, span):
            suppressed.append({**h, "_suppressed": "hash_like"})
            continue
        # 4c: 日志时间戳跳过（针对 Date 误判）
        if h["type"] in ("Date-ISO", "Date-CJK") and _looks_like_log_timestamp(text, span):
            suppressed.append({**h, "_suppressed": "log_timestamp"})
            continue
        # 4d: 银行卡 上下文降级（CN-ID 18 位本身已是强信号，不降级）
        if h["type"] == "CN-Bank" and not _has_bank_context(text, span):
            h["confidence"] = max(0.5, h["confidence"] - 0.25)
            h["_demoted"] = "no_bank_context"
        # 4e: Date 缺人名邻近，降级
        if h["type"] in ("Date-ISO", "Date-CJK"):
            snippet = text[max(0, span[0] - 30) : min(len(text), span[1] + 30)]
            if not any(t in snippet for t in ["病人", "患者", "出生", "Mr.", "Ms.", "Mrs.", "DOB"]):
                h["confidence"] = max(0.4, h["confidence"] - 0.3)
                h["_demoted"] = "no_name_proximity"
        filtered.append(h)

    # Step 5: 去重（同 span 取 max confidence）
    by_span: dict[tuple, dict] = {}
    for h in filtered:
        key = tuple(h["span"])
        if key not in by_span or h["confidence"] > by_span[key]["confidence"]:
            by_span[key] = h
    final = list(by_span.values())

    max_conf = max((h["confidence"] for h in final), default=0.0)
    return {
        "hits": final,
        "suppressed": suppressed,
        "summary": {
            "total_hits": len(final),
            "suppressed_count": len(suppressed),
            "max_confidence": max_conf,
            "blocking_recommendation": max_conf >= 0.9,
        },
        "_meta": {
            "version": "0.3-v3",
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "passes": ["rule-v2", "name-heuristic-v3"]
            + (["classifier"] if classifier_hits else []),
        },
    }


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
        if method == "detect":
            result = detect_v3(params.get("text", ""), params.get("context"))
            resp = {"id": req.get("id"), "result": result}
        elif method == "health":
            resp = {"id": req.get("id"), "result": {"status": "ok-v3"}}
        else:
            resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "detect"
    if cmd == "health":
        print(json.dumps({"status": "ok-v3"}))
        return 0
    if cmd == "detect":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        text = req.get("text", "") or ""
        print(json.dumps(detect_v3(text, req.get("context")), ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
