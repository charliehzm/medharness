"""Async NLP-lite catch for outbound PHI reflow misses.

This module is intentionally stdlib-only and side-effect free. It returns only
hashes of matched spans so callers can emit findings without carrying raw PHI.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

MAX_RESPONSE_CHARS = 16_384

EntityType = Literal["CN_NAME", "MRN"]

_CN_CONTEXT_CUES = ("患者", "姓名", "病人", "床号", "家属", "主诉")
_MRN_CONTEXT_CUES = ("病案号", "住院号", "门诊号", "就诊卡号", "病历号", "MRN")
_TWO_CHAR_SURNAMES = (
    "欧阳",
    "司马",
    "诸葛",
    "上官",
    "司徒",
    "东方",
    "独孤",
    "南宫",
    "夏侯",
    "尉迟",
    "公孙",
    "皇甫",
    "令狐",
    "宇文",
    "长孙",
    "慕容",
    "轩辕",
    "赫连",
    "澹台",
    "端木",
    "公羊",
    "拓跋",
    "乐正",
    "鲜于",
    "申屠",
    "仲孙",
)
_SINGLE_CHAR_SURNAMES = frozenset(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹"
    "曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任卢姚姜崔钟谭陆汪"
    "范金石廖贾夏韦傅方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺"
    "顾毛郝龚邵万钱严覃武戴莫孔向汤"
)
_CN_BAD_SUFFIXES = (
    "医生",
    "主任",
    "护士",
    "患者",
    "病人",
    "家属",
    "报告",
    "检查",
    "诊断",
    "治疗",
    "复查",
    "处理",
    "建议",
    "记录",
)
_CN_BOUNDARY_BIGRAMS = (
    "今日",
    "今天",
    "昨日",
    "昨天",
    "明日",
    "明天",
    "复诊",
    "检查",
    "报告",
    "处理",
    "入院",
    "出院",
    "主诉",
    "医嘱",
    "建议",
    "完成",
)

_HAN = r"[\u4e00-\u9fff]"
_TWO_CHAR_SURNAME_PATTERN = "|".join(re.escape(item) for item in _TWO_CHAR_SURNAMES)
_SINGLE_CHAR_SURNAME_PATTERN = "".join(sorted(_SINGLE_CHAR_SURNAMES))
_CN_NAME_RE = re.compile(
    rf"(?P<compound>{_TWO_CHAR_SURNAME_PATTERN}){_HAN}{{1,2}}"
    rf"|(?P<single>[{_SINGLE_CHAR_SURNAME_PATTERN}]){_HAN}{{1,2}}"
)
_ALNUM_RUN_RE = re.compile(r"[A-Za-z0-9]{6,}")


@dataclass(frozen=True)
class CatchFinding:
    entity_type: EntityType
    score: float
    start: int
    end: int
    value_sha256: str

    def to_event_dict(self) -> dict[str, object]:
        return {
            "entity_type": self.entity_type,
            "score": self.score,
            "start": self.start,
            "end": self.end,
            "value_sha256": self.value_sha256,
        }


def scan_missed(text: str) -> tuple[CatchFinding, ...]:
    if not isinstance(text, str):
        raise TypeError("text must be str")

    capped = text[:MAX_RESPONSE_CHARS]
    findings: list[CatchFinding] = []
    seen: set[tuple[EntityType, int, int]] = set()

    for finding in _scan_cn_names(capped):
        key = (finding.entity_type, finding.start, finding.end)
        if key not in seen:
            findings.append(finding)
            seen.add(key)

    for finding in _scan_mrns(capped):
        key = (finding.entity_type, finding.start, finding.end)
        if key not in seen:
            findings.append(finding)
            seen.add(key)

    return tuple(sorted(findings, key=lambda item: (item.start, item.end, item.entity_type)))


def _scan_cn_names(text: str) -> tuple[CatchFinding, ...]:
    findings: list[CatchFinding] = []
    for match in _CN_NAME_RE.finditer(text):
        value = match.group(0)
        end = match.end()
        value, end = _trim_cn_context_suffix(text, value, end)
        if _looks_like_cn_false_positive(value):
            continue

        score = _cn_context_score(text, match.start(), end)
        if score <= 0.0:
            continue

        findings.append(
            CatchFinding(
                entity_type="CN_NAME",
                score=score,
                start=match.start(),
                end=end,
                value_sha256=_sha256(value),
            )
        )
    return tuple(findings)


def _scan_mrns(text: str) -> tuple[CatchFinding, ...]:
    findings: list[CatchFinding] = []
    for match in _ALNUM_RUN_RE.finditer(text):
        score = _mrn_context_score(text, match.start(), match.end())
        if score <= 0.0:
            continue

        findings.append(
            CatchFinding(
                entity_type="MRN",
                score=score,
                start=match.start(),
                end=match.end(),
                value_sha256=_sha256(match.group(0)),
            )
        )
    return tuple(findings)


def _cn_context_score(text: str, start: int, end: int) -> float:
    left = text[max(0, start - 8) : start]
    right = text[end : min(len(text), end + 8)]
    has_strong_left = any(cue in left for cue in ("患者", "姓名", "病人", "家属"))
    has_any_cue = has_strong_left or any(cue in left or cue in right for cue in _CN_CONTEXT_CUES)
    if not has_any_cue:
        return 0.0
    if has_strong_left:
        return 0.91
    return 0.84


def _mrn_context_score(text: str, start: int, end: int) -> float:
    left = text[max(0, start - 18) : start]
    right = text[end : min(len(text), end + 12)]
    if any(cue in left or cue in right for cue in _MRN_CONTEXT_CUES):
        return 0.93
    return 0.0


def _looks_like_cn_false_positive(value: str) -> bool:
    return any(value.endswith(suffix) for suffix in _CN_BAD_SUFFIXES)


def _trim_cn_context_suffix(text: str, value: str, end: int) -> tuple[str, int]:
    if end >= len(text) or len(value) < 3:
        return value, end
    if value[-1] + text[end] in _CN_CONTEXT_CUES + _CN_BOUNDARY_BIGRAMS:
        return value[:-1], end - 1
    return value, end


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
