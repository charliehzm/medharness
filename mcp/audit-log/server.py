#!/usr/bin/env python3
"""
mcp-audit-log · M2/M3 起步实现（本地 append-only + 哈希链）
============================================================
M3 升级：切 ClickHouse + 对象存储 WORM。
本文件提供 append / query / verify / seal_bundle 四端点。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path


def _store_dir() -> Path:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    d = project_dir / ".audit" / "worm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger_path() -> Path:
    # 按日分文件，便于冷热分离
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return _store_dir() / f"ledger_{today}.jsonl"


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_last_hash() -> str:
    files = sorted(_store_dir().glob("ledger_*.jsonl"))
    for f in reversed(files):
        with open(f, "rb") as fh:
            last = None
            for line in fh:
                if line.strip():
                    last = line
            if last:
                rec = json.loads(last.decode())
                return rec.get("self_hash", "sha256:GENESIS")
    return "sha256:GENESIS"


_EVENT_TYPES_CACHE = None


def _load_event_types() -> dict:
    """读 mcp/audit-log/event_types.yml；不存在则返回宽松模式"""
    global _EVENT_TYPES_CACHE
    if _EVENT_TYPES_CACHE is not None:
        return _EVENT_TYPES_CACHE
    yml_path = Path(__file__).parent / "event_types.yml"
    if not yml_path.exists():
        _EVENT_TYPES_CACHE = {"_relaxed": True, "by_name": {}}
        return _EVENT_TYPES_CACHE
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        by_name = {e["name"]: e for e in (data.get("event_types") or [])}
        _EVENT_TYPES_CACHE = {
            "_relaxed": False,
            "by_name": by_name,
            "severities": set(data.get("severities") or []),
        }
    except Exception:
        _EVENT_TYPES_CACHE = {"_relaxed": True, "by_name": {}}
    return _EVENT_TYPES_CACHE


def _validate_event(event: dict) -> str | None:
    """返回 None 表示通过；否则返回错误原因。"""
    schema = _load_event_types()
    if schema.get("_relaxed"):
        return None  # 无 schema 文件 → 宽松通过（M2 占位）
    et = event.get("event_type")
    if not et:
        return "event_type missing"
    if et not in schema["by_name"]:
        return f"event_type '{et}' not in enum (see mcp/audit-log/event_types.yml)"
    spec = schema["by_name"][et]
    required = spec.get("required_fields") or []
    payload = event.get("payload") or {}
    # change_id / session_id 也可能在 event 顶层
    pool = {**event, **payload}
    for k in required:
        if k not in pool or pool[k] in (None, ""):
            return f"required field '{k}' missing for event_type '{et}'"
    return None


def append(event: dict) -> dict:
    event = dict(event)
    err = _validate_event(event)
    if err:
        raise ValueError(f"schema violation: {err}")
    event["id"] = event.get("id") or str(uuid.uuid4())
    event["ts"] = event.get("ts") or (datetime.utcnow().isoformat() + "Z")
    event["prev_hash"] = _read_last_hash()
    base = {k: v for k, v in event.items() if k != "self_hash"}
    event["self_hash"] = _hash(_canonical(base))

    ledger = _ledger_path()
    # 简易 fail-loud：写不进去就报错
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def query(change_id: str | None = None, event_type: str | None = None, limit: int = 1000) -> dict:
    results = []
    for f in sorted(_store_dir().glob("ledger_*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if change_id and rec.get("change_id") != change_id:
                    continue
                if event_type and rec.get("event_type") != event_type:
                    continue
                results.append(rec)
                if len(results) >= limit:
                    return {"records": results, "truncated": True}
    return {"records": results, "truncated": False}


def verify(change_id: str | None = None) -> dict:
    prev = "sha256:GENESIS"
    bad = []
    count = 0
    for f in sorted(_store_dir().glob("ledger_*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                count += 1
                if rec.get("prev_hash") != prev:
                    bad.append(
                        {
                            "id": rec.get("id"),
                            "reason": "prev_hash_mismatch",
                            "expected": prev,
                            "got": rec.get("prev_hash"),
                        }
                    )
                base = {k: v for k, v in rec.items() if k != "self_hash"}
                expect = _hash(_canonical(base))
                if rec.get("self_hash") != expect:
                    bad.append({"id": rec.get("id"), "reason": "self_hash_mismatch"})
                prev = rec.get("self_hash", prev)
    return {"records_checked": count, "tampered": bad, "ok": not bad}


def seal_bundle(change_id: str, root_sha256: str, manifest_hash: str) -> dict:
    receipt = append(
        {
            "event_type": "bundle_seal",
            "change_id": change_id,
            "payload": {"root_sha256": root_sha256, "manifest_hash": manifest_hash},
        }
    )
    return {
        "receipt_id": receipt["id"],
        "storage_uri": str(_ledger_path()),
        "receipt_hash": receipt["self_hash"],
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
        try:
            if method == "append":
                result = append(params)
            elif method == "query":
                result = query(
                    params.get("change_id"), params.get("event_type"), params.get("limit", 1000)
                )
            elif method == "verify":
                result = verify(params.get("change_id"))
            elif method == "seal_bundle":
                result = seal_bundle(
                    params["change_id"], params["root_sha256"], params["manifest_hash"]
                )
            elif method == "health":
                result = {"status": "ok", "ledger_dir": str(_store_dir())}
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


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"

    if cmd == "health":
        print(json.dumps({"status": "ok", "ledger_dir": str(_store_dir())}))
        return 0

    if cmd == "append":
        req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        try:
            print(json.dumps(append(req), ensure_ascii=False))
            return 0
        except ValueError as e:
            print(
                json.dumps({"error": "schema_violation", "detail": str(e)}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 2

    if cmd == "query":
        req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        print(
            json.dumps(
                query(req.get("change_id"), req.get("event_type"), req.get("limit", 1000)),
                ensure_ascii=False,
            )
        )
        return 0

    if cmd == "verify":
        req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        print(json.dumps(verify(req.get("change_id")), ensure_ascii=False))
        return 0

    if cmd == "seal_bundle":
        req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        print(
            json.dumps(
                seal_bundle(req["change_id"], req["root_sha256"], req["manifest_hash"]),
                ensure_ascii=False,
            )
        )
        return 0

    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
