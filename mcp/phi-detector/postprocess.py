"""Context post-processing for phi-detector v3.

>>> spans = [Span(0, 5, "CN_ID", 0.9), Span(0, 5, "CN_DRIVERS_LICENSE", 0.82)]
>>> apply_context_rules("驾驶证 110101199001011237", spans, 0.6)[0].entity_type
'CN_DRIVERS_LICENSE'
>>> len(_SESSION_CACHE)
1
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any

try:
    from .recognizers.cn_core import classify_placeholder
    from .recognizers.cn_finance_travel import is_valid_cn_bank
except ImportError:  # pragma: no cover - direct local execution
    from recognizers.cn_core import classify_placeholder
    from recognizers.cn_finance_travel import is_valid_cn_bank

CACHE_TTL_SECONDS = 60
CACHE_MAX_SIZE = 10_000

LOG_LEVEL_RE = re.compile(r"\b(?:INFO|ERROR|DEBUG|WARN)\b", re.I)
POSITIVE_NAME_CONTEXT = ("患者", "病人", "医生", "护士")
NEGATIVE_NAME_CONTEXT = ("员工", "用户", "Co-Author", "作者", "contributor")

ENTITY_PRIORITY = {
    "CN_DRIVERS_LICENSE": 95,
    "CN_ID": 90,
    "CN_BANK": 85,
    "CN_PASSPORT": 80,
    "CN_HK_ID": 80,
    "CN_PHONE": 75,
    "CN_MRN": 75,
    "CN_NAME": 70,
    "PERSON": 65,
}

_SESSION_CACHE: OrderedDict[
    tuple[str, tuple[tuple[int, int, str, float], ...], float], tuple[float, list[Span]]
] = OrderedDict()


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    score: float
    metadata: dict[str, Any] | None = None


def apply_context_rules(text: str, spans: list[Any], score_threshold: float = 0.6) -> list[Span]:
    """Apply context rules and return thresholded, deduplicated spans."""
    normalized = [_to_span(span) for span in spans]
    key = _cache_key(text, normalized, score_threshold)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    processed: list[Span] = []
    for span in normalized:
        value = text[span.start : span.end]
        if _is_placeholder(value):
            continue
        current = span
        current = _demote_log_timestamp(text, current)
        current = _weight_name_context(text, current)
        current = _strict_cn_bank(value, current)
        if current.score >= score_threshold:
            processed.append(current)
    result = _dedup_spans(processed)
    _cache_set(key, result)
    return result


def _to_span(span: Any) -> Span:
    if isinstance(span, Span):
        return span
    if isinstance(span, dict):
        return Span(
            start=int(span["start"]),
            end=int(span["end"]),
            entity_type=str(span.get("entity_type", span.get("type"))),
            score=float(span.get("score", span.get("confidence", 0.0))),
            metadata=span.get("metadata"),
        )
    return Span(
        start=int(span.start),
        end=int(span.end),
        entity_type=str(span.entity_type),
        score=float(span.score),
        metadata=getattr(span, "recognition_metadata", None),
    )


def _is_placeholder(value: str) -> bool:
    return classify_placeholder(value) is not None or value in {"<phi>", "${phi}"}


def _demote_log_timestamp(text: str, span: Span) -> Span:
    window = text[max(0, span.start - 50) : min(len(text), span.end + 50)]
    if LOG_LEVEL_RE.search(window):
        return replace(span, score=max(0.0, span.score * 0.2))
    return span


def _weight_name_context(text: str, span: Span) -> Span:
    if span.entity_type not in {"CN_NAME", "PERSON"}:
        return span
    window = text[max(0, span.start - 20) : min(len(text), span.end + 20)]
    score = span.score
    if any(keyword in window for keyword in POSITIVE_NAME_CONTEXT):
        score *= 1.3
    if any(keyword in window for keyword in NEGATIVE_NAME_CONTEXT):
        score *= 0.5
    return replace(span, score=min(score, 1.0))


def _strict_cn_bank(value: str, span: Span) -> Span:
    if span.entity_type == "CN_BANK" and not is_valid_cn_bank(value):
        return replace(span, score=min(span.score, 0.0))
    return span


def _dedup_spans(spans: list[Span]) -> list[Span]:
    selected: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.start, -(s.end - s.start), -s.score)):
        overlaps = [existing for existing in selected if _overlaps(span, existing)]
        if not overlaps:
            selected.append(span)
            continue
        candidates = [span, *overlaps]
        if any((item.start, item.end) == (span.start, span.end) for item in overlaps):
            winner = max(candidates, key=_same_span_rank)
        else:
            winner = max(candidates, key=_overlap_span_rank)
        selected = [existing for existing in selected if existing not in overlaps]
        selected.append(winner)
    return sorted(selected, key=lambda s: (s.start, s.end))


def _overlaps(left: Span, right: Span) -> bool:
    return left.start < right.end and right.start < left.end


def _overlap_span_rank(span: Span) -> tuple[float, int, int]:
    return (span.score, ENTITY_PRIORITY.get(span.entity_type, 0), span.end - span.start)


def _same_span_rank(span: Span) -> tuple[int, float, int]:
    return (ENTITY_PRIORITY.get(span.entity_type, 0), span.score, span.end - span.start)


def _cache_key(
    text: str,
    spans: list[Span],
    score_threshold: float,
) -> tuple[str, tuple[tuple[int, int, str, float], ...], float]:
    return (
        sha256(text.encode("utf-8")).hexdigest(),
        tuple((span.start, span.end, span.entity_type, round(span.score, 6)) for span in spans),
        score_threshold,
    )


def _cache_get(
    key: tuple[str, tuple[tuple[int, int, str, float], ...], float],
) -> list[Span] | None:
    now = time.monotonic()
    item = _SESSION_CACHE.get(key)
    if item is None:
        return None
    created_at, value = item
    if now - created_at > CACHE_TTL_SECONDS:
        _SESSION_CACHE.pop(key, None)
        return None
    _SESSION_CACHE.move_to_end(key)
    return list(value)


def _cache_set(
    key: tuple[str, tuple[tuple[int, int, str, float], ...], float],
    value: list[Span],
) -> None:
    _SESSION_CACHE[key] = (time.monotonic(), list(value))
    _SESSION_CACHE.move_to_end(key)
    while len(_SESSION_CACHE) > CACHE_MAX_SIZE:
        _SESSION_CACHE.popitem(last=False)
