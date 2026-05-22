from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "model-router"))

from allowlist import AllowlistError, HotAllowlist, load_allowlist  # noqa: E402


def _vendor_families_path(tmp_path: Path) -> Path:
    path = tmp_path / "vendor_families.yml"
    path.write_text(
        """schema_version: T3.vendor_families.v1
families:
  openai:
    - gpt-5
  alibaba:
    - qwen-max
  anthropic:
    - claude-sonnet-4.6
""",
        encoding="utf-8",
    )
    return path


def _allowlist_payload(**overrides: object) -> dict[str, object]:
    model = {
        "id": "qwen-max",
        "vendor_family": "alibaba",
        "deployment": "private://qwen-max",
        "allowed_agent_roles": ["coder", "compliance", "docs"],
        "allowed_data_levels": ["L1", "L2", "L3"],
        "rate_limit_qps": 10,
    }
    top_level: dict[str, object] = {
        "schema_version": "T3.allowlist.v1",
        "policy_version": "change-t3.2",
        "models": [model],
    }
    for key, value in overrides.items():
        if key.startswith("model__"):
            model[key.removeprefix("model__")] = value
        else:
            top_level[key] = value
    return top_level


def _write_allowlist(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_happy_path_loads_lookup_and_model_list(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(tmp_path / "MODEL_ALLOWLIST.json", _allowlist_payload())

    allowlist = load_allowlist(allowlist_path, vendor_families_path=vendors)

    entry = allowlist.lookup("qwen-max")
    assert entry is not None
    assert entry.vendor_family == "alibaba"
    assert entry.allowed_agent_roles == ("coder", "compliance", "docs")
    assert entry.allowed_data_levels == ("L1", "L2", "L3")
    assert allowlist.lookup("missing") is None
    assert allowlist.all_models() == ["qwen-max"]
    assert allowlist.active_policy_version() == "change-t3.2"


def test_missing_top_level_key_fails_closed(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(tmp_path / "MODEL_ALLOWLIST.json", _allowlist_payload())
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    del payload["policy_version"]
    _write_allowlist(allowlist_path, payload)

    with pytest.raises(AllowlistError, match="missing required top-level key 'policy_version'"):
        load_allowlist(allowlist_path, vendor_families_path=vendors)


def test_unknown_vendor_family_fails_closed(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(
        tmp_path / "MODEL_ALLOWLIST.json",
        _allowlist_payload(model__vendor_family="unknown-family"),
    )

    with pytest.raises(AllowlistError, match="not declared in vendor_families.yml"):
        load_allowlist(allowlist_path, vendor_families_path=vendors)


def test_invalid_data_level_fails_closed(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(
        tmp_path / "MODEL_ALLOWLIST.json",
        _allowlist_payload(model__allowed_data_levels=["L1", "L5"]),
    )

    with pytest.raises(AllowlistError, match="allowed_data_levels contains invalid values"):
        load_allowlist(allowlist_path, vendor_families_path=vendors)


def test_non_positive_rate_limit_fails_closed(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(
        tmp_path / "MODEL_ALLOWLIST.json",
        _allowlist_payload(model__rate_limit_qps=0),
    )

    with pytest.raises(AllowlistError, match="rate_limit_qps must be positive integer"):
        load_allowlist(allowlist_path, vendor_families_path=vendors)


def test_allowed_agent_roles_must_be_non_empty(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(
        tmp_path / "MODEL_ALLOWLIST.json",
        _allowlist_payload(model__allowed_agent_roles=[]),
    )

    with pytest.raises(AllowlistError, match="allowed_agent_roles must be non-empty"):
        load_allowlist(allowlist_path, vendor_families_path=vendors)


def test_hot_allowlist_reloads_after_file_change(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(tmp_path / "MODEL_ALLOWLIST.json", _allowlist_payload())
    hot = HotAllowlist(allowlist_path, vendor_families_path=vendors)

    first = hot.get_allowlist()
    updated_payload = _allowlist_payload(policy_version="change-t3.2b", model__id="gpt-5")
    updated_payload["models"][0]["vendor_family"] = "openai"  # type: ignore[index]
    updated_payload["models"][0]["deployment"] = "private://gpt-5"  # type: ignore[index]
    time.sleep(0.01)
    _write_allowlist(allowlist_path, updated_payload)

    second = hot.get_allowlist()

    assert first.active_policy_version() == "change-t3.2"
    assert second.active_policy_version() == "change-t3.2b"
    assert second.all_models() == ["gpt-5"]


def test_hot_allowlist_keeps_old_active_when_new_file_is_broken(tmp_path: Path) -> None:
    vendors = _vendor_families_path(tmp_path)
    allowlist_path = _write_allowlist(tmp_path / "MODEL_ALLOWLIST.json", _allowlist_payload())
    hot = HotAllowlist(allowlist_path, vendor_families_path=vendors)
    first = hot.get_allowlist()

    allowlist_path.write_text("{", encoding="utf-8")
    second = hot.get_allowlist()

    assert second is first
    assert second.all_models() == ["qwen-max"]
