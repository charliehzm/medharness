"""mcp-pm-bridge · community-edition local ticket store + JSONL audit.

Covers: create -> get -> list -> update-status roundtrip; invalid status rejected;
unknown ticket handled; notify attaches a note to a known ticket; sync_change /
health return real (non-placeholder) payloads; JSONL audit trail is appended;
timestamps are tz-aware UTC (Z-suffixed, no naive utcnow); 0-PHI. The server module
is loaded directly via importlib (mirrors test_a0_auth_login.py); CLAUDE_PROJECT_DIR
is pointed at a tmp dir so the audit file lands in isolation.
"""

from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PM_DIR = ROOT / "mcp" / "pm-bridge"

_spec = util.spec_from_file_location("pm_bridge_server", PM_DIR / "server.py")
assert _spec is not None and _spec.loader is not None
pm = util.module_from_spec(_spec)
sys.modules["pm_bridge_server"] = pm
_spec.loader.exec_module(pm)

_PHI_MARKERS = ("患者姓名", "身份证", "手机号", "病案号", "13800138000", "110101")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fresh in-memory ticket store + audit dir under tmp per test."""
    monkeypatch.setattr(pm, "_TICKETS", {})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    yield


def test_create_get_list_update_roundtrip() -> None:
    created = pm.create_compliance_ticket(
        {
            "title": "PHI 泄漏复核",
            "description": "排查日志脱敏",
            "severity": "high",
            "change_id": "chg-001",
        }
    )
    tid = created["id"]
    assert tid.startswith("PM-") and len(tid) == len("PM-") + 8
    assert created["status"] == "open"
    assert created["severity"] == "high"
    assert created["change_id"] == "chg-001"
    assert "占位" not in json.dumps(created, ensure_ascii=False)
    assert "_note" not in created

    fetched = pm.get_ticket({"ticket_id": tid})
    assert fetched["id"] == tid
    assert fetched["title"] == "PHI 泄漏复核"

    listed = pm.list_tickets({})
    assert listed["count"] == 1
    assert listed["tickets"][0]["id"] == tid

    updated = pm.update_ticket_status({"ticket_id": tid, "status": "in_progress"})
    assert updated["status"] == "in_progress"
    assert "updated_at" in updated
    assert pm.get_ticket({"ticket_id": tid})["status"] == "in_progress"


def test_list_tickets_filters_by_status() -> None:
    a = pm.create_compliance_ticket({"title": "A"})
    b = pm.create_compliance_ticket({"title": "B"})
    pm.update_ticket_status({"ticket_id": b["id"], "status": "resolved"})

    open_ids = {t["id"] for t in pm.list_tickets({"status": "open"})["tickets"]}
    resolved_ids = {t["id"] for t in pm.list_tickets({"status": "resolved"})["tickets"]}
    assert open_ids == {a["id"]}
    assert resolved_ids == {b["id"]}
    assert pm.list_tickets({})["count"] == 2


def test_create_requires_title() -> None:
    out = pm.create_compliance_ticket({"description": "no title"})
    assert out["created"] is False
    assert pm.list_tickets({})["count"] == 0


def test_invalid_severity_defaults_to_medium() -> None:
    t = pm.create_compliance_ticket({"title": "X", "severity": "bogus"})
    assert t["severity"] == "medium"


def test_update_status_rejects_invalid_status() -> None:
    t = pm.create_compliance_ticket({"title": "X"})
    out = pm.update_ticket_status({"ticket_id": t["id"], "status": "done"})
    assert out["updated"] is False
    # store unchanged
    assert pm.get_ticket({"ticket_id": t["id"]})["status"] == "open"


def test_get_and_update_unknown_ticket() -> None:
    assert pm.get_ticket({"ticket_id": "PM-deadbeef"})["found"] is False
    out = pm.update_ticket_status({"ticket_id": "PM-deadbeef", "status": "resolved"})
    assert out["updated"] is False


def test_notify_attaches_note_to_known_ticket() -> None:
    t = pm.create_compliance_ticket({"title": "X"})
    out = pm.notify({"ticket_id": t["id"], "message": "已通知合规负责人"})
    assert out["notified"] is True
    assert out["ticket_id"] == t["id"]
    assert out["note_count"] == 1
    assert pm.get_ticket({"ticket_id": t["id"]})["notes"][0]["message"] == "已通知合规负责人"


def test_notify_unknown_ticket_still_records() -> None:
    out = pm.notify({"ticket_id": "PM-missing", "message": "hi"})
    assert out["notified"] is True
    assert "ticket_id" not in out  # not attached, but still audited


def test_sync_change_returns_real_payload() -> None:
    out = pm.sync_change({"change_id": "chg-xyz"})
    assert out["synced"] is True
    assert out["change_id"] == "chg-xyz"
    assert "占位" not in json.dumps(out, ensure_ascii=False)
    assert "_note" not in out


def test_health_reports_ticket_count() -> None:
    assert pm.health() == {"status": "ok", "tickets": 0}
    pm.create_compliance_ticket({"title": "X"})
    h = pm.health()
    assert h == {"status": "ok", "tickets": 1}
    assert "placeholder" not in json.dumps(h)


def test_audit_jsonl_is_appended(tmp_path: Path) -> None:
    pm.create_compliance_ticket({"title": "audited"})
    pm.sync_change({"change_id": "c1"})
    audit_file = tmp_path / ".audit" / "pm_bridge.jsonl"
    assert audit_file.exists()
    lines = [ln for ln in audit_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    events = {json.loads(ln)["event"] for ln in lines}
    assert events == {"create_compliance_ticket", "sync_change"}


def test_timestamp_is_tz_aware_utc() -> None:
    t = pm.create_compliance_ticket({"title": "X"})
    ts = t["created_at"]
    assert ts.endswith("Z")
    # parseable as an aware datetime, normalized to UTC
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_no_phi_in_payloads() -> None:
    t = pm.create_compliance_ticket({"title": "合规复核", "description": "数据分级与审计留痕检查"})
    blob = json.dumps(t, ensure_ascii=False) + json.dumps(pm.list_tickets({}), ensure_ascii=False)
    for marker in _PHI_MARKERS:
        assert marker not in blob
