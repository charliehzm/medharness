#!/usr/bin/env python3
"""Seed the medical channel TEMPLATES into new-api as DISABLED, keyless channels.

Reads deploy/presets/channel-templates.medical.json and creates one new-api channel per
template — key left BLANK and status=disabled — so NOTHING is callable until an operator
fills in the real key / base_url and meets the compliance prerequisites (no-retention /
境内 driving contract / private deployment). Idempotent: skips a channel whose name
already exists. This script NEVER writes a real key or a live (enabled) channel; it
refuses any template that carries a non-empty key.

Run inside the A0 container, which can reach new-api:

    docker cp scripts/seed_medical_channels.py medharness-a0-api:/tmp/
    docker cp deploy/presets/channel-templates.medical.json medharness-a0-api:/tmp/
    docker exec medharness-a0-api python /tmp/seed_medical_channels.py \
        --templates /tmp/channel-templates.medical.json --dry-run     # preview
    docker exec medharness-a0-api python /tmp/seed_medical_channels.py \
        --templates /tmp/channel-templates.medical.json               # create (disabled)
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.request
from pathlib import Path

NEW_API = os.environ.get("NEW_API_URL", "http://new-api:3000").rstrip("/")
USER = os.environ.get("NEW_API_ROOT_USERNAME", "admin")
PW = os.environ.get("NEW_API_ROOT_PASSWORD", "medharness123")

DEFAULT_TEMPLATES = Path(__file__).resolve().parents[1] / "deploy" / "presets" / "channel-templates.medical.json"

# new-api channel type ints (constant/channel.go); covers the provider names the medical
# templates use. Unknown -> refuse (a wrong int would silently mis-route).
TYPE_NAME_TO_INT = {
    "openai": 1, "azure": 3, "ollama": 4, "custom": 8, "openai-compatible": 8,
    "anthropic": 14, "claude": 14, "baidu": 15, "baichuan": 15, "zhipu": 16,
    "ali": 17, "qwen": 17, "dashscope": 17, "gemini": 24, "google": 24,
    "moonshot": 25, "deepseek": 43, "siliconflow": 40, "vllm": 47, "xinference": 47,
}
STATUS_NAME_TO_INT = {"enabled": 1, "disabled": 2}

# new-api's validateChannel refuses an empty key on add, so a seeded template gets an
# obviously-fake placeholder key (the operator MUST replace it). The channel is created
# disabled, so the placeholder is never used to call anything.
PLACEHOLDER_KEY = "REPLACE_WITH_REAL_KEY_BEFORE_ENABLING"


def _call(opener, path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(NEW_API + path, data=data, method=method or ("POST" if body is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    req.add_header("New-Api-User", "1")
    with opener.open(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


def _existing_names(opener) -> set[str]:
    data = _call(opener, "/api/channel/?p=1&size=200").get("data")
    items = data.get("items") if isinstance(data, dict) else data
    return {c.get("name") for c in (items or []) if isinstance(c, dict)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed disabled, keyless medical channel templates into new-api.")
    ap.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES, help="path to channel-templates.medical.json")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, create nothing")
    args = ap.parse_args()

    doc = json.loads(args.templates.read_text(encoding="utf-8"))
    channels = doc.get("channels", [])
    if not channels:
        print("no channel templates found", file=sys.stderr)
        return 1

    # Honesty guard: refuse to seed anything that is not a blank-key, disabled template.
    for ch in channels:
        if ch.get("key"):
            print(f"REFUSING: template {ch.get('name')!r} carries a non-empty key", file=sys.stderr)
            return 2
        if ch.get("status") != "disabled":
            print(f"REFUSING: template {ch.get('name')!r} is not status=disabled", file=sys.stderr)
            return 2
        if str(ch.get("type", "")).lower() not in TYPE_NAME_TO_INT:
            print(f"REFUSING: template {ch.get('name')!r} has unknown type {ch.get('type')!r}", file=sys.stderr)
            return 2

    if args.dry_run:
        print(f"[dry-run] would seed {len(channels)} DISABLED, keyless channels into {NEW_API}:")
        for ch in channels:
            mh = ch.get("medharness", {})
            print(f"  · {ch['name']}  type={ch['type']}->{TYPE_NAME_TO_INT[ch['type'].lower()]} "
                  f"models={','.join(ch.get('models', []))} group={ch.get('group')} "
                  f"lane={mh.get('lane')} region={mh.get('region')} cap={mh.get('data_level_cap')}  [placeholder key · disabled]")
        return 0

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login = _call(opener, "/api/user/login", {"username": USER, "password": PW})
    if not login.get("success"):
        print("new-api admin login failed", file=sys.stderr)
        return 1

    existing = _existing_names(opener)
    created = skipped = 0
    for ch in channels:
        if ch["name"] in existing:
            print(f"  skip (exists): {ch['name']}")
            skipped += 1
            continue
        wrapped = {"mode": "single", "channel": {
            "name": ch["name"],
            "type": TYPE_NAME_TO_INT[ch["type"].lower()],
            "key": PLACEHOLDER_KEY,  # obvious placeholder — operator MUST replace it
            "base_url": ch.get("base_url", ""),
            "models": ",".join(ch.get("models", [])),
            "group": ch.get("group", "default"),
            "status": STATUS_NAME_TO_INT["disabled"],
        }}
        res = _call(opener, "/api/channel/", wrapped)
        if res.get("success"):
            print(f"  created (disabled): {ch['name']}")
            created += 1
        else:
            print(f"  FAILED: {ch['name']}: {res.get('message')}", file=sys.stderr)
    print(f"done: {created} created, {skipped} skipped (already present). All DISABLED with a "
          f"placeholder key ({PLACEHOLDER_KEY!r}) — replace key + base_url and meet the compliance "
          f"prerequisites before enabling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
