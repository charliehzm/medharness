#!/usr/bin/env python3
"""Rule-based prompt-injection detector.

Offline, deterministic, and stdlib-only.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

CATEGORY_INDIRECT = "indirect_injection"
CATEGORY_TOOL_ABUSE = "tool_abuse"
CATEGORY_ROLE_ESCALATION = "role_escalation"
CATEGORY_JAILBREAK = "jailbreak"
CATEGORY_ENCODING = "encoding_obfuscation"

ALL_CATEGORIES = (
    CATEGORY_INDIRECT,
    CATEGORY_TOOL_ABUSE,
    CATEGORY_ROLE_ESCALATION,
    CATEGORY_JAILBREAK,
    CATEGORY_ENCODING,
)

CATEGORY_PRIORITY = {
    CATEGORY_ROLE_ESCALATION: 5,
    CATEGORY_INDIRECT: 4,
    CATEGORY_TOOL_ABUSE: 3,
    CATEGORY_JAILBREAK: 2,
    CATEGORY_ENCODING: 1,
}

BLOCK_THRESHOLD = float(os.getenv("PROMPT_INJECTION_BLOCK_THRESHOLD", "0.5"))
MIN_TEXT_LENGTH = 10

_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.S)
_QUOTED_SPAN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
_SYSTEM_PREFIX_RE = re.compile(r"(?i)\bsystem:\s*")
_BASE64_CANDIDATE_RE = re.compile(r"(?:[A-Za-z0-9+/]{40,}={0,2})")

_CONFUSABLE_TRANSLATION = str.maketrans(
    {
        "а": "a",
        "А": "A",
        "е": "e",
        "Е": "E",
        "о": "o",
        "О": "O",
        "р": "p",
        "Р": "P",
        "с": "c",
        "С": "C",
        "х": "x",
        "Х": "X",
        "у": "y",
        "У": "Y",
        "і": "i",
        "І": "I",
        "ѕ": "s",
        "Ѕ": "S",
        "ј": "j",
        "Ј": "J",
    }
)


@dataclass(frozen=True)
class DetectionResult:
    """Result of prompt-injection detection."""

    blocked: bool
    category: str | None = None
    score: float = 0.0
    matched_rules: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    category: str
    score: float
    pattern: re.Pattern[str] | None = None
    matcher: Callable[[str], list[tuple[int, int]]] | None = None
    zh_bonus: float = 0.0


def _match_base64_candidates(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _BASE64_CANDIDATE_RE.finditer(text):
        token = match.group(0)
        if len(token) < 40:
            continue
        if not any(char in token for char in "+/="):
            continue
        if token.count("=") > 2:
            continue
        spans.append(match.span())
    return spans


def _match_homoglyph_suspicious(text: str) -> list[tuple[int, int]]:
    normalized = unicodedata.normalize("NFKC", text).translate(_CONFUSABLE_TRANSLATION)
    if normalized == text:
        return []

    lowered = normalized.casefold()
    suspicious_markers = (
        "ignore",
        "admin",
        "root",
        "system",
        "developer mode",
        "execute",
        "shell",
        "dan",
    )
    if any(marker in lowered for marker in suspicious_markers):
        return [(0, len(text))]
    return []


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "indirect_ignore_instructions",
        CATEGORY_INDIRECT,
        0.62,
        pattern=re.compile(
            r"(?i)(?:\bignore\s+(?:previous|prior|all)\s+instructions\b"
            r"|忽略(?:之前|先前|所有)(?:的)?指令)",
        ),
        zh_bonus=0.10,
    ),
    _Rule(
        "indirect_disregard_prior",
        CATEGORY_INDIRECT,
        0.42,
        pattern=re.compile(
            r"(?i)(?:\bdisregard\s+(?:above|prior|previous)\b"
            r"|无视(?:上方|先前|以上))",
        ),
        zh_bonus=0.08,
    ),
    _Rule(
        "indirect_system_boundary",
        CATEGORY_INDIRECT,
        0.38,
        pattern=re.compile(r"(?i)(?:\n{2,}\s*system:\s*|\[system\]:|</s><s>)"),
    ),
    _Rule(
        "tool_shell_exec",
        CATEGORY_TOOL_ABUSE,
        0.55,
        pattern=re.compile(
            r"(?i)(?:\brun\s+shell\b|\bexecute\b|\beval\s*\(|\bsubprocess\b"
            r"|\bos\.system\b|\bsh\s+-c\b)",
        ),
    ),
    _Rule(
        "tool_fs_abuse",
        CATEGORY_TOOL_ABUSE,
        0.60,
        pattern=re.compile(
            r"(?i)(?:\brm\s+-rf\b|\bcat\s+/etc/passwd\b|/dev/null)",
        ),
    ),
    _Rule(
        "tool_network_exfil",
        CATEGORY_TOOL_ABUSE,
        0.58,
        pattern=re.compile(
            r"(?i)(?:\bcurl\s+https?://\S+|\bwget\s+https?://\S+"
            r"|\bexfiltrate\b|\bsend\s+to\s+https?://\S+)",
        ),
    ),
    _Rule(
        "role_you_are_admin",
        CATEGORY_ROLE_ESCALATION,
        0.68,
        pattern=re.compile(
            r"(?i)(?:\byou are (?:an? )?(?:admin|root|developer|system)\b"
            r"|你现在是(?:一个)?(?:管理员|超级管理员|开发者|系统))",
        ),
        zh_bonus=0.10,
    ),
    _Rule(
        "role_act_as_admin",
        CATEGORY_ROLE_ESCALATION,
        0.62,
        pattern=re.compile(
            r"(?i)(?:\bact as (?:an? )?(?:admin|superuser)\b"
            r"|扮演(?:一个)?(?:管理员|超级管理员|系统管理员))",
        ),
        zh_bonus=0.10,
    ),
    _Rule(
        "role_developer_mode",
        CATEGORY_ROLE_ESCALATION,
        0.52,
        pattern=re.compile(
            r"(?i)(?:\bdeveloper mode\b|\bjailbroken\b|\bunrestricted\b"
            r"|解除限制|无视规则|进入开发者模式)",
        ),
        zh_bonus=0.08,
    ),
    _Rule(
        "jailbreak_dan",
        CATEGORY_JAILBREAK,
        0.64,
        pattern=re.compile(
            r"(?i)(?:\bDAN\b|\bdo anything now\b|\bignore all OpenAI policies\b)",
        ),
    ),
    _Rule(
        "jailbreak_response_without_filter",
        CATEGORY_JAILBREAK,
        0.55,
        pattern=re.compile(
            r"(?i)(?:\[INSERT: any content\]|\{response_without_filter\}"
            r"|\bresponse_without_filter\b)",
        ),
    ),
    _Rule(
        "jailbreak_escape_sequences",
        CATEGORY_JAILBREAK,
        0.42,
        pattern=re.compile(r"(?:\\\\n|\\u0000|\\x1b)"),
    ),
    _Rule(
        "encoding_base64",
        CATEGORY_ENCODING,
        0.56,
        matcher=_match_base64_candidates,
    ),
    _Rule(
        "encoding_zero_width",
        CATEGORY_ENCODING,
        0.58,
        pattern=re.compile(r"[\u200b\u200c\u200d]"),
    ),
    _Rule(
        "encoding_homoglyph",
        CATEGORY_ENCODING,
        0.52,
        matcher=_match_homoglyph_suspicious,
    ),
)

_ENGLISH_BOOST_MARKERS = (
    "ignore previous instructions",
    "ignore prior instructions",
    "run shell",
    "execute",
    "you are admin",
    "act as admin",
    "developer mode",
    "do anything now",
    "ignore all openai policies",
    "response_without_filter",
)

_CHINESE_BOOST_MARKERS = (
    "忽略",
    "无视",
    "你现在是",
    "扮演",
    "管理员",
    "开发者模式",
    "解除限制",
    "系统",
)

__all__ = [
    "ALL_CATEGORIES",
    "BLOCK_THRESHOLD",
    "CATEGORY_ENCODING",
    "CATEGORY_INDIRECT",
    "CATEGORY_JAILBREAK",
    "CATEGORY_ROLE_ESCALATION",
    "CATEGORY_TOOL_ABUSE",
    "DetectionResult",
    "detect_injection",
]


def detect_injection(text: str, context: dict[str, Any] | None = None) -> DetectionResult:
    """Detect prompt-injection patterns in text.

    Fail closed on internal errors. Never logs raw text.
    """

    try:
        return _score_text(text, context)
    except Exception:
        LOGGER.warning("prompt-injection detector failed closed")
        return DetectionResult(
            blocked=True,
            category=None,
            score=1.0,
            matched_rules=[],
            reason="detector internal error - fail closed",
        )


def _score_text(text: str, context: dict[str, Any] | None) -> DetectionResult:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    normalized_context = dict(context or {})
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_LENGTH:
        return DetectionResult(
            blocked=False,
            category=None,
            score=0.0,
            matched_rules=[],
            reason="empty input" if not stripped else "input too short",
        )

    scan_text = _mask_fenced_code_blocks(text)
    quote_spans = _quoted_spans(scan_text)

    category_scores = {category: 0.0 for category in ALL_CATEGORIES}
    matched_rules: list[str] = []

    for rule in _RULES:
        contribution = _rule_contribution(rule, scan_text, quote_spans, normalized_context)
        if contribution <= 0.0:
            continue
        category_scores[rule.category] = min(1.0, category_scores[rule.category] + contribution)
        matched_rules.append(rule.rule_id)

    _apply_context_boosts(category_scores, text, normalized_context)

    blocked_categories = [
        category
        for category in ALL_CATEGORIES
        if category_scores[category] >= _effective_threshold(category, normalized_context)
    ]
    top_category, top_score = _top_category(category_scores)

    if blocked_categories:
        category = max(blocked_categories, key=lambda item: CATEGORY_PRIORITY[item])
        score = category_scores[category]
        reason = f"blocked by {category} score={score:.2f} rules={','.join(matched_rules)}"
        return DetectionResult(
            blocked=True,
            category=category,
            score=score,
            matched_rules=matched_rules,
            reason=reason,
        )

    if top_category is None:
        return DetectionResult(
            blocked=False,
            category=None,
            score=0.0,
            matched_rules=[],
            reason="no suspicious patterns",
        )

    reason = (
        f"matched {top_category} score={top_score:.2f} "
        f"below threshold={_effective_threshold(top_category, normalized_context):.2f} "
        f"rules={','.join(matched_rules)}"
    )
    return DetectionResult(
        blocked=False,
        category=None,
        score=top_score,
        matched_rules=matched_rules,
        reason=reason,
    )


def _rule_contribution(
    rule: _Rule,
    text: str,
    quote_spans: list[tuple[int, int]],
    context: dict[str, Any],
) -> float:
    spans = _rule_spans(rule, text)
    if not spans:
        return 0.0

    factors: list[float] = []
    for start, end in spans:
        factor = 1.0
        if _span_inside_any(start, end, quote_spans):
            factor *= 0.5
        if str(context.get("language", "")).lower() == "zh" and rule.zh_bonus:
            factor *= 1.0 + rule.zh_bonus
        factors.append(factor)

    return min(1.0, rule.score * max(factors))


def _rule_spans(rule: _Rule, text: str) -> list[tuple[int, int]]:
    if rule.pattern is not None:
        return [match.span() for match in rule.pattern.finditer(text)]
    if rule.matcher is not None:
        return rule.matcher(text)
    return []


def _apply_context_boosts(
    category_scores: dict[str, float],
    text: str,
    context: dict[str, Any],
) -> None:
    if _has_multilingual_markers(text):
        for category, score in category_scores.items():
            if score > 0:
                category_scores[category] = min(1.0, score * 1.2)

    if _system_prefix_count(text) >= 5:
        top_category, _ = _top_category(category_scores)
        if top_category is not None:
            category_scores[top_category] = min(1.0, category_scores[top_category] + 0.3)

    if str(context.get("language", "")).lower() == "zh" and _contains_cjk(text):
        for category, score in category_scores.items():
            if score > 0:
                category_scores[category] = min(1.0, score * 1.05)


def _effective_threshold(category: str, context: dict[str, Any]) -> float:
    threshold = BLOCK_THRESHOLD
    if category == CATEGORY_INDIRECT and str(context.get("data_source", "")).lower() == "rag":
        return max(0.35, threshold - 0.10)
    return threshold


def _top_category(category_scores: dict[str, float]) -> tuple[str | None, float]:
    populated = [(category, score) for category, score in category_scores.items() if score > 0]
    if not populated:
        return None, 0.0
    category, score = max(
        populated,
        key=lambda item: (item[1], CATEGORY_PRIORITY[item[0]]),
    )
    return category, score


def _mask_fenced_code_blocks(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return _FENCED_BLOCK_RE.sub(_replace, text)


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in _QUOTED_SPAN_RE.finditer(text)]


def _span_inside_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start >= span_start and end <= span_end for span_start, span_end in spans)


def _system_prefix_count(text: str) -> int:
    return len(_SYSTEM_PREFIX_RE.findall(text))


def _has_multilingual_markers(text: str) -> bool:
    lowered = text.lower()
    has_english = any(marker in lowered for marker in _ENGLISH_BOOST_MARKERS)
    has_chinese = any(marker in text for marker in _CHINESE_BOOST_MARKERS)
    return has_english and has_chinese


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))
