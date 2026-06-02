from __future__ import annotations

import sys
from importlib import util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROUTER_DIR = ROOT / "mcp" / "model-router"
ALLOWLIST_PATH = MODEL_ROUTER_DIR / "allowlist.py"
DEV_ALLOWLIST = ROOT / "deploy" / "dev" / "model_allowlist.dev.json"
VENDOR_FAMILIES = MODEL_ROUTER_DIR / "vendor_families.yml"

sys.path.insert(0, str(MODEL_ROUTER_DIR))

spec = util.spec_from_file_location("model_router_allowlist_dev", ALLOWLIST_PATH)
assert spec is not None
allowlist_module = util.module_from_spec(spec)
sys.modules["model_router_allowlist_dev"] = allowlist_module
assert spec.loader is not None
spec.loader.exec_module(allowlist_module)


def test_dev_allowlist_loads_gpt4o_entry() -> None:
    allowlist = allowlist_module.load_allowlist(
        DEV_ALLOWLIST,
        vendor_families_path=VENDOR_FAMILIES,
    )

    entry = allowlist.lookup("gpt-4o")

    assert entry is not None
    assert "gpt-4o" in allowlist.all_models()
    assert "coder" in entry.allowed_agent_roles
    assert "L2" in entry.allowed_data_levels
