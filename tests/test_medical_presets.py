"""Validate the medical onboarding presets (allowlist + channel templates).

Offline guard for deploy/presets/: the starter allowlist must actually load through
the real model-router loader (schema + declared vendor families), and both presets must
honour the catalog's compliance rules — PHI (L3/L4) only on a private deployment, never
on an overseas/regular channel — while shipping ZERO real keys and only disabled channel
templates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "deploy" / "presets"
ROUTER_DIR = ROOT / "mcp" / "model-router"
sys.path.insert(0, str(ROUTER_DIR))

from allowlist import load_allowlist  # noqa: E402

ALLOWLIST_PATH = PRESETS / "medical-allowlist.default.json"
TEMPLATES_PATH = PRESETS / "channel-templates.medical.json"
VENDOR_FAMILIES = ROUTER_DIR / "vendor_families.yml"


def _allowlist():
    return load_allowlist(ALLOWLIST_PATH, vendor_families_path=VENDOR_FAMILIES)


def test_allowlist_loads_through_the_real_router_loader() -> None:
    al = _allowlist()
    assert al.schema_version == "T3.allowlist.v1"
    assert al.policy_version == "medical-default-v1"
    assert len(al.entries) >= 7, "starter allowlist should cover the §4 menu"


def test_phi_levels_only_on_private_deployments() -> None:
    # The compliance heart: an entry may carry L3/L4 (PHI) ONLY if it is a private
    # deployment; an overseas channel must never carry PHI.
    for entry in _allowlist().entries:
        levels = set(entry.allowed_data_levels)
        carries_phi = bool(levels & {"L3", "L4"})
        if carries_phi:
            assert entry.deployment.startswith("private://"), (
                f"{entry.id} carries PHI levels {sorted(levels)} on non-private deployment "
                f"{entry.deployment}"
            )
        if entry.deployment.startswith("overseas://"):
            assert not carries_phi, (
                f"overseas model {entry.id} must default-deny PHI, got {sorted(levels)}"
            )
        assert "L1" in levels or "L2" in levels, f"{entry.id} must allow at least a baseline level"


def test_templates_carry_no_real_keys_and_are_disabled() -> None:
    doc = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    blob = json.dumps(doc, ensure_ascii=False)
    assert "sk-" not in blob, "channel templates must ship ZERO real keys"
    channels = doc["channels"]
    assert channels, "expected channel templates"
    for ch in channels:
        assert ch.get("key", "") == "", f"template {ch['name']} must have a blank key"
        assert ch.get("status") == "disabled", f"template {ch['name']} must be disabled"
        mh = ch.get("medharness", {})
        assert mh.get("lane") in {"regular", "sensitive"}, f"{ch['name']}: bad lane"
        assert mh.get("region") in {"cn", "overseas", "private"}, f"{ch['name']}: bad region"
        # Only a private/sensitive channel may declare an L4 cap.
        if mh.get("data_level_cap") in {"L3", "L4"}:
            assert mh.get("region") == "private" and mh.get("lane") == "sensitive", (
                f"{ch['name']} caps at PHI but is not a private sensitive channel"
            )


def test_every_allowlist_model_has_a_channel_template() -> None:
    al_models = {e.id for e in _allowlist().entries}
    doc = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    tmpl_models = {m for ch in doc["channels"] for m in ch.get("models", [])}
    missing = al_models - tmpl_models
    assert not missing, f"allowlist models without a channel template: {sorted(missing)}"
