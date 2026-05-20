#!/usr/bin/env python3
"""
mcp-desensitize · M1 占位实现
==============================
M2 完整实现要点：
- 接 phi-detector 命中清单做替换
- KMS 集成（M1 占位用本地 fernet 密钥）
- reverse 带 token 校验
- MCP 协议（stdio/sse）封装

本占位提供 CLI 形态的 desensitize / reverse / health 子命令。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sys
import uuid
from datetime import datetime

# === 占位符规则（与 phi-detector 对齐） ===
SUBSTITUTIONS = [
    ("CN-ID", re.compile(r"\b\d{17}[\dXx]\b"), "ID"),
    ("CN-Phone", re.compile(r"\b1[3-9]\d{9}\b"), "PH"),
    ("Email", re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "EM"),
]


def _stable_short_id(original: str, salt: str) -> str:
    digest = hmac.new(salt.encode(), original.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(digest)[:4].decode().lower()


def desensitize(text: str, change_id: str = "unknown") -> dict:
    salt = f"desensitize::{change_id}::session"
    mapping: dict[str, str] = {}
    new_text = text

    for _, pat, tcode in SUBSTITUTIONS:
        for m in list(pat.finditer(new_text)):
            original = m.group()
            short = _stable_short_id(original, salt)
            placeholder = f"{{{{ {tcode}_{short} }}}}"
            if placeholder not in mapping:
                mapping[placeholder] = original
        # 第二遍替换（避免 finditer 与替换交叉）
        new_text = pat.sub(
            lambda mm: next(ph for ph, orig in mapping.items() if orig == mm.group()), new_text
        )

    map_id = str(uuid.uuid4())
    return {
        "desensitized": new_text,
        "map_id": map_id,
        "map_ref": f"local-placeholder://{map_id}",  # M2 改为 kms://...
        "_unsafe_map_preview_count": len(mapping),
        "residual_risk": [],
        "_meta": {
            "version": "0.1-placeholder",
            "ts": datetime.utcnow().isoformat() + "Z",
        },
    }


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "desensitize"

    if cmd == "health":
        print(
            json.dumps(
                {
                    "status": "ok-placeholder",
                    "kms": "not-integrated (M1)",
                }
            )
        )
        return 0

    if cmd == "desensitize":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        text = req.get("payload", "")
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        result = desensitize(text, req.get("change_id", "unknown"))
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if cmd == "reverse":
        # M1: 拒绝 reverse —— 未集成 KMS 不允许返回明文
        print(
            json.dumps(
                {"error": "reverse not available in M1 placeholder. Requires KMS integration."}
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
