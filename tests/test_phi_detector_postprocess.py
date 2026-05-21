from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp" / "phi-detector"))

from postprocess import _SESSION_CACHE, CACHE_MAX_SIZE, Span, apply_context_rules  # noqa: E402


def setup_function(function: object) -> None:
    del function
    _SESSION_CACHE.clear()


def test_placeholder_suppressed() -> None:
    spans = [Span(3, 21, "CN_ID", 0.95)]
    assert apply_context_rules("ID 110101199001011234", spans) == []


def test_log_timestamp_demoted_below_threshold() -> None:
    text = "INFO 2026-05-21T10:00:00Z request done"
    spans = [Span(5, 25, "DATE_TIME", 0.9)]
    assert apply_context_rules(text, spans, 0.6) == []


def test_name_context_boost_and_demote() -> None:
    boosted = apply_context_rules("患者 张小明 今日复诊", [Span(3, 6, "CN_NAME", 0.6)], 0.7)
    demoted = apply_context_rules("员工 张小明 提交代码", [Span(3, 6, "CN_NAME", 0.8)], 0.6)
    assert boosted[0].score > 0.7
    assert demoted == []


def test_session_cache_lru_limit() -> None:
    for index in range(CACHE_MAX_SIZE + 1):
        apply_context_rules(f"患者 张{index}", [Span(3, 5, "CN_NAME", 0.8)], 0.6)
    assert len(_SESSION_CACHE) == CACHE_MAX_SIZE


def test_session_cache_key_does_not_store_raw_text() -> None:
    apply_context_rules("患者 张小明", [Span(3, 6, "CN_NAME", 0.8)], 0.6)
    cache_key = next(iter(_SESSION_CACHE))
    assert cache_key[0] != "患者 张小明"
    assert len(cache_key[0]) == 64


def test_cn_bank_strictness_drops_invalid_luhn() -> None:
    spans = [Span(4, 20, "CN_BANK", 0.95)]
    assert apply_context_rules("银行卡 6222021234567890", spans) == []


def test_span_dedup_prefers_drivers_license_over_cn_id_when_context_matches() -> None:
    text = "驾驶证 110101199001011237"
    start = text.index("110101")
    end = len(text)
    spans = [Span(start, end, "CN_ID", 0.95), Span(start, end, "CN_DRIVERS_LICENSE", 0.82)]
    result = apply_context_rules(text, spans, 0.6)
    assert len(result) == 1
    assert result[0].entity_type == "CN_DRIVERS_LICENSE"
