#!/usr/bin/env python3
"""
mcp-desensitize v2 · M2 升级版
================================
新增能力：
1. KMS 集成（M2 用 Fernet 占位，M3 起切真实 KMS）
2. reverse 端点（受控环境 + token 校验）
3. 日期保留间隔（per-change 随机 offset）
4. MCP stdio 骨架
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import SUBSTITUTIONS, _stable_short_id  # noqa: E402


# ====== KMS 占位 ======
# M3 起替换为真实 KMS（阿里云 KMS / AWS KMS / Vault）

_FERNET_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    pass


def _kms_get_key(change_id: str) -> bytes:
    """获取/创建 per-change key。M2 占位用本地派生；M3 起强制 KMS。"""
    salt = os.environ.get("KMS_SALT", "M2-DEV-ONLY-NOT-FOR-PROD")
    digest = hashlib.sha256(f"{salt}::{change_id}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_map(mapping: dict, change_id: str) -> str:
    if not _FERNET_AVAILABLE:
        # 退化：仅 base64（M1/M2-early 占位；M2 完整版要求 cryptography 已安装）
        raw = json.dumps(mapping, ensure_ascii=False).encode()
        return "PLACEHOLDER:" + base64.b64encode(raw).decode()
    key = _kms_get_key(change_id)
    f = Fernet(key)
    raw = json.dumps(mapping, ensure_ascii=False).encode()
    return "FERNET:" + f.encrypt(raw).decode()


def _decrypt_map(blob: str, change_id: str) -> dict:
    if blob.startswith("PLACEHOLDER:"):
        raw = base64.b64decode(blob[len("PLACEHOLDER:"):])
        return json.loads(raw.decode())
    if blob.startswith("FERNET:"):
        if not _FERNET_AVAILABLE:
            raise RuntimeError("cryptography not installed")
        key = _kms_get_key(change_id)
        f = Fernet(key)
        raw = f.decrypt(blob[len("FERNET:"):].encode())
        return json.loads(raw.decode())
    raise ValueError("unknown map blob format")


# ====== 替换逻辑（含日期保留间隔） ======

def _date_offset_days(change_id: str) -> int:
    digest = hashlib.sha256(f"date-offset::{change_id}".encode()).digest()
    # 偏移 ±90 天
    return int.from_bytes(digest[:2], "big") % 180 - 90


def _shift_date(match: re.Match, offset_days: int) -> str:
    raw = match.group()
    for fmt_in, fmt_out in [("%Y-%m-%d", "%Y-%m-%d"), ("%Y/%m/%d", "%Y/%m/%d"), ("%Y年%m月%d日", "%Y年%m月%d日")]:
        try:
            dt = datetime.strptime(raw, fmt_in)
            return (dt + timedelta(days=offset_days)).strftime(fmt_out)
        except ValueError:
            continue
    return raw  # 无法解析则原样返回


DATE_PAT = re.compile(r"\b\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?\b")


def desensitize_v2(text: str, change_id: str = "unknown", preserve_intervals: bool = True) -> dict:
    salt = f"desensitize::{change_id}::session"
    mapping: dict[str, str] = {}
    new_text = text

    # Pass A: 占位符替换
    for _, pat, tcode in SUBSTITUTIONS:
        def _replace(m, tcode=tcode):
            original = m.group()
            short = _stable_short_id(original, salt)
            placeholder = f"{{{{ {tcode}_{short} }}}}"
            mapping[placeholder] = original
            return placeholder
        new_text = pat.sub(_replace, new_text)

    # Pass B: 日期偏移（保留间隔）
    if preserve_intervals:
        offset = _date_offset_days(change_id)

        def _date_replace(m):
            shifted = _shift_date(m, offset)
            mapping[shifted] = m.group()  # 反向映射记录原始日期
            return shifted
        new_text = DATE_PAT.sub(_date_replace, new_text)

    map_id = str(uuid.uuid4())
    encrypted = _encrypt_map(mapping, change_id)

    # M2: map 内容编码后短暂返回；M3 起仅返回 reference（不返回内容）
    return {
        "desensitized": new_text,
        "map_id": map_id,
        "map_ref": f"kms-placeholder://{change_id}/{map_id}",
        "map_blob": encrypted,  # M3 起移除本字段，强制走 mcp-audit-log
        "stats": {
            "placeholders_count": len([k for k in mapping if "{{" in k]),
            "dates_shifted": preserve_intervals,
        },
        "_meta": {
            "version": "0.2-v2",
            "ts": datetime.utcnow().isoformat() + "Z",
            "fernet_available": _FERNET_AVAILABLE,
        },
    }


def reverse(desensitized: str, map_blob: str, change_id: str, kms_token: str | None) -> dict:
    """需要 token，否则拒绝。M2 占位 token = env COMPLIANCE_REVERSE_TOKEN。"""
    expected = os.environ.get("COMPLIANCE_REVERSE_TOKEN")
    if not expected or kms_token != expected:
        return {"error": "token invalid or missing; reverse denied",
                "audit": "denied"}
    mapping = _decrypt_map(map_blob, change_id)
    restored = desensitized
    for placeholder, original in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        restored = restored.replace(placeholder, original)
    return {
        "original": restored,
        "_audit": {
            "ts": datetime.utcnow().isoformat() + "Z",
            "change_id": change_id,
            "reversed_count": len(mapping),
        }
    }


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        # MCP stdio 模式（简化版）
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
            if method == "desensitize":
                result = desensitize_v2(params.get("payload", ""), params.get("change_id", "unknown"))
                resp = {"id": req.get("id"), "result": result}
            elif method == "reverse":
                result = reverse(params.get("desensitized", ""), params.get("map_blob", ""),
                                 params.get("change_id", ""), params.get("kms_token"))
                resp = {"id": req.get("id"), "result": result}
            elif method == "health":
                resp = {"id": req.get("id"), "result": {"status": "ok-v2",
                        "fernet_available": _FERNET_AVAILABLE}}
            else:
                resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0

    cmd = sys.argv[1] if len(sys.argv) > 1 else "desensitize"
    if cmd == "health":
        print(json.dumps({"status": "ok-v2", "fernet_available": _FERNET_AVAILABLE}))
        return 0
    if cmd == "desensitize":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        text = req.get("payload", "")
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        print(json.dumps(desensitize_v2(text, req.get("change_id", "unknown")), ensure_ascii=False))
        return 0
    if cmd == "reverse":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        result = reverse(req.get("desensitized", ""), req.get("map_blob", ""),
                         req.get("change_id", ""), req.get("kms_token"))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
