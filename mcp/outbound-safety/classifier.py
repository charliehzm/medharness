"""Pure rules-only decision core for B1 outbound response safety.

B1.1 intentionally has no network, model, audit, or detector imports. Runtime
adapters inject ``phi_scan`` in later leaves.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

MAX_RESPONSE_CHARS = 16_384

ClassificationType = Literal["phi_reflow", "harmful", "hallucination"]
DecisionName = Literal["pass", "desensitized", "blocked", "warned"]
Disposition = Literal["block", "desensitize", "warn"]

PhiScan = Callable[[str, Mapping[str, object]], "PhiScanResult | Mapping[str, object]"]


@dataclass(frozen=True)
class PhiScanResult:
    has_phi: bool
    sanitized_text: str | None = None
    score: float = 1.0
    entities: tuple[str, ...] = ()


@dataclass(frozen=True)
class Classification:
    type: ClassificationType
    score: float
    disposition: Disposition


@dataclass(frozen=True)
class Decision:
    decision: DecisionName
    classifications: tuple[Classification, ...]
    sanitized_text: str | None
    event_ref: str
    stats: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "classifications": [asdict(item) for item in self.classifications],
            "sanitized_text": self.sanitized_text,
            "event_ref": self.event_ref,
            "stats": dict(self.stats),
        }


@dataclass(frozen=True)
class _Rule:
    kind: ClassificationType
    pattern: re.Pattern[str]
    score: float
    disposition: Disposition


HARMFUL_RULES: tuple[_Rule, ...] = (
    _Rule(
        "harmful",
        re.compile(
            r"\b(kill yourself|suicide method|self[- ]?harm|poison dosage|make a bomb)\b"
            r"|自杀|自残|服毒|投毒|制作爆炸物|爆炸物",
            re.IGNORECASE,
        ),
        0.96,
        "block",
    ),
)

HALLUCINATION_RULES: tuple[_Rule, ...] = (
    _Rule(
        "hallucination",
        re.compile(
            r"\b(guaranteed cure|stop all medication|do not see a doctor|replace your doctor)\b"
            r"|保证治愈|无需就医|不用看医生|停止所有药|立即停药|一定是癌|肯定是癌",
            re.IGNORECASE,
        ),
        0.78,
        "warn",
    ),
)


def classify(
    response_text: str,
    context: Mapping[str, object],
    policy: Mapping[str, str],
    *,
    phi_scan: PhiScan,
) -> Decision:
    """Classify outbound model response text using rules and an injected PHI scanner."""

    if not isinstance(response_text, str):
        raise TypeError("response_text must be str")
    if len(response_text) > MAX_RESPONSE_CHARS:
        raise ValueError("response_text exceeds max length")

    started = time.perf_counter()
    classifications: list[Classification] = []
    sanitized_text: str | None = None
    normalized_policy = _normalize_policy(policy)

    phi_result = _scan_phi_fail_closed(response_text, context, phi_scan)
    if phi_result.has_phi:
        phi_disposition = normalized_policy["phi_reflow"]
        classifications.append(
            Classification(
                type="phi_reflow",
                score=_clamp_score(phi_result.score),
                disposition=phi_disposition,
            )
        )
        if phi_disposition == "desensitize":
            sanitized_text = _safe_sanitized_text(phi_result.sanitized_text, response_text)

    classifications.extend(_match_rules(response_text, HARMFUL_RULES))
    classifications.extend(_match_rules(response_text, HALLUCINATION_RULES))

    decision = _final_decision(classifications)
    if decision != "desensitized":
        sanitized_text = None

    return Decision(
        decision=decision,
        classifications=tuple(classifications),
        sanitized_text=sanitized_text,
        event_ref="",
        stats={"duration_ms": max(0.0, (time.perf_counter() - started) * 1000)},
    )


def _scan_phi_fail_closed(
    response_text: str,
    context: Mapping[str, object],
    phi_scan: PhiScan,
) -> PhiScanResult:
    try:
        return _coerce_phi_scan_result(phi_scan(response_text, context))
    except Exception:
        return PhiScanResult(has_phi=True, sanitized_text=None, score=1.0, entities=("unknown",))


def _coerce_phi_scan_result(result: PhiScanResult | Mapping[str, object]) -> PhiScanResult:
    if isinstance(result, PhiScanResult):
        return result

    spans = result.get("spans")
    has_phi = bool(result.get("has_phi") or result.get("detected") or spans)
    score = result.get("score", 1.0 if has_phi else 0.0)
    sanitized_text = result.get("sanitized_text")
    entities = result.get("entities", ())
    if not entities and isinstance(spans, list):
        entities = tuple(
            str(item.get("entity_type", "unknown")) for item in spans if isinstance(item, dict)
        )

    return PhiScanResult(
        has_phi=has_phi,
        sanitized_text=sanitized_text if isinstance(sanitized_text, str) else None,
        score=_clamp_score(score),
        entities=tuple(str(item) for item in entities)
        if isinstance(entities, (tuple, list))
        else (),
    )


def _normalize_policy(policy: Mapping[str, str]) -> dict[str, Disposition]:
    phi_reflow = policy.get("phi_reflow", "block")
    return {
        "phi_reflow": "desensitize" if phi_reflow == "desensitize" else "block",
        "harmful": "block",
        "hallucination": "warn",
    }


def _match_rules(response_text: str, rules: tuple[_Rule, ...]) -> list[Classification]:
    matches: list[Classification] = []
    for rule in rules:
        if rule.pattern.search(response_text):
            matches.append(
                Classification(
                    type=rule.kind,
                    score=rule.score,
                    disposition=rule.disposition,
                )
            )
    return matches


def _final_decision(classifications: list[Classification]) -> DecisionName:
    if any(item.disposition == "block" for item in classifications):
        return "blocked"
    if any(item.disposition == "desensitize" for item in classifications):
        return "desensitized"
    if any(item.disposition == "warn" for item in classifications):
        return "warned"
    return "pass"


def _safe_sanitized_text(candidate: str | None, original: str) -> str:
    if not candidate or candidate == original or original in candidate:
        return "__PHI_REDACTED__"
    return candidate


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))
