"""Core CN recognizers for phi-detector v3.

The module is intentionally importable without ``presidio_analyzer`` installed so
local safety checks can still compile in minimal development environments.

>>> is_valid_cn_id("110101199001011237")
True
>>> is_valid_cn_id("110101199001011234")
False
>>> classify_placeholder("110101199001011234")
'placeholder'
>>> is_valid_cn_phone("13800138000")
False
>>> is_valid_cn_phone("13912345678")
True
>>> CNMrnRecognizer().analyze("MRN AB12345678", ["CN_MRN"], "zh")[0].entity_type
'CN_MRN'
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:  # pragma: no cover - exercised in environments with presidio installed.
    from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
except Exception:  # pragma: no cover - lightweight fallback for bootstrap envs.

    @dataclass(frozen=True)
    class Pattern:  # type: ignore[no-redef]
        name: str
        regex: str
        score: float

    @dataclass
    class RecognizerResult:  # type: ignore[no-redef]
        entity_type: str
        start: int
        end: int
        score: float
        analysis_explanation: object | None = None
        recognition_metadata: dict | None = None

    class PatternRecognizer:  # type: ignore[no-redef]
        def __init__(
            self,
            supported_entity: str,
            patterns: list[Pattern],
            context: list[str] | None = None,
            supported_language: str = "zh",
            name: str | None = None,
        ) -> None:
            self.supported_entities = [supported_entity]
            self.supported_language = supported_language
            self.patterns = patterns
            self.context = context or []
            self.name = name or supported_entity

        def analyze(
            self,
            text: str,
            entities: list[str],
            nlp_artifacts: object | None = None,
        ) -> list[RecognizerResult]:
            del nlp_artifacts
            if self.supported_entities[0] not in entities:
                return []
            results: list[RecognizerResult] = []
            for pattern in self.patterns:
                for match in re.finditer(pattern.regex, text):
                    results.append(
                        RecognizerResult(
                            entity_type=self.supported_entities[0],
                            start=match.start(),
                            end=match.end(),
                            score=pattern.score,
                        )
                    )
            return results


CN_ID_ENTITY = "CN_ID"
CN_PHONE_ENTITY = "CN_PHONE"
CN_MRN_ENTITY = "CN_MRN"

CN_ID_PATTERN = re.compile(
    r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
)
CN_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
CN_MRN_PATTERN = re.compile(r"\b([A-Z]{2}\d{8}|MRN[-_ ]?[A-Z0-9]{6,12})\b")

CN_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
CN_ID_CHECKSUM = "10X98765432"
CN_PHONE_PREFIXES = {
    "130",
    "131",
    "132",
    "133",
    "134",
    "135",
    "136",
    "137",
    "138",
    "139",
    "145",
    "146",
    "147",
    "148",
    "149",
    "150",
    "151",
    "152",
    "153",
    "155",
    "156",
    "157",
    "158",
    "159",
    "162",
    "165",
    "166",
    "167",
    "170",
    "171",
    "172",
    "173",
    "175",
    "176",
    "177",
    "178",
    "180",
    "181",
    "182",
    "183",
    "184",
    "185",
    "186",
    "187",
    "188",
    "189",
    "190",
    "191",
    "192",
    "193",
    "195",
    "196",
    "197",
    "198",
    "199",
}

PLACEHOLDERS = {
    "110101199001011234",
    "13800138000",
    "ID-XXX",
    "<phi>",
    "${phi}",
}


def classify_placeholder(value: str) -> str | None:
    """Return ``placeholder`` for public examples that should not block."""
    return "placeholder" if value.strip() in PLACEHOLDERS else None


def is_valid_cn_id(value: str) -> bool:
    """Validate an 18-digit Mainland China ID checksum."""
    normalized = value.strip().upper()
    if classify_placeholder(normalized) or not CN_ID_PATTERN.fullmatch(normalized):
        return False
    checksum_index = (
        sum(int(digit) * CN_ID_WEIGHTS[index] for index, digit in enumerate(normalized[:17])) % 11
    )
    return normalized[-1] == CN_ID_CHECKSUM[checksum_index]


def is_valid_cn_phone(value: str) -> bool:
    """Validate a Mainland China mobile number by prefix and placeholder list."""
    normalized = value.strip()
    return (
        classify_placeholder(normalized) is None
        and CN_PHONE_PATTERN.fullmatch(normalized) is not None
        and normalized[:3] in CN_PHONE_PREFIXES
    )


def _metadata(kind: str) -> dict[str, str]:
    return {"recognizer": kind, "source": "medharness-cn-core"}


class CNIdRecognizer(PatternRecognizer):
    """Recognizer for checksum-valid CN citizen IDs."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_ID_ENTITY,
            patterns=[Pattern(name="cn_id_18", regex=CN_ID_PATTERN.pattern, score=0.85)],
            context=["身份证", "证件号", "公民身份号码", "ID"],
            supported_language="zh",
            name="medharness_cn_id",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_ID_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.95,
                recognition_metadata=_metadata("cn_id"),
            )
            for match in CN_ID_PATTERN.finditer(text)
            if CN_ID_ENTITY in entities and is_valid_cn_id(match.group(1))
        ]


class CNPhoneRecognizer(PatternRecognizer):
    """Recognizer for CN mobile numbers with carrier prefix validation."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_PHONE_ENTITY,
            patterns=[Pattern(name="cn_mobile", regex=CN_PHONE_PATTERN.pattern, score=0.82)],
            context=["手机", "电话", "联系", "手机号"],
            supported_language="zh",
            name="medharness_cn_phone",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_PHONE_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.9,
                recognition_metadata=_metadata("cn_phone"),
            )
            for match in CN_PHONE_PATTERN.finditer(text)
            if CN_PHONE_ENTITY in entities and is_valid_cn_phone(match.group(1))
        ]


class CNMrnRecognizer(PatternRecognizer):
    """Recognizer for generic synthetic hospital MRN formats."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_MRN_ENTITY,
            patterns=[Pattern(name="cn_mrn", regex=CN_MRN_PATTERN.pattern, score=0.78)],
            context=["病案号", "住院号", "MRN", "病历号"],
            supported_language="zh",
            name="medharness_cn_mrn",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_MRN_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.86,
                recognition_metadata=_metadata("cn_mrn"),
            )
            for match in CN_MRN_PATTERN.finditer(text)
            if CN_MRN_ENTITY in entities
        ]
