"""Medical-context CN recognizers for phi-detector v3.

>>> CNAddressRecognizer().analyze("住址 北京市朝阳区建国路1号", ["CN_ADDRESS"], None)[0].entity_type
'CN_ADDRESS'
>>> CNDiseaseCodeRecognizer().analyze("诊断 ICD-10: E11.9", ["CN_DISEASE_CODE"], None)[0].entity_type
'CN_DISEASE_CODE'
>>> CNDiseaseCodeRecognizer().analyze("commit E11.9", ["CN_DISEASE_CODE"], None)
[]
>>> CNDrugCodeRecognizer().analyze("药品 国药准字H20012345", ["CN_DRUG_CODE"], None)[0].entity_type
'CN_DRUG_CODE'
"""

from __future__ import annotations

import re

try:
    from .cn_core import Pattern, PatternRecognizer, RecognizerResult, classify_placeholder
except ImportError:  # pragma: no cover - direct doctest execution
    from cn_core import Pattern, PatternRecognizer, RecognizerResult, classify_placeholder

CN_ADDRESS_ENTITY = "CN_ADDRESS"
CN_DISEASE_CODE_ENTITY = "CN_DISEASE_CODE"
CN_DRUG_CODE_ENTITY = "CN_DRUG_CODE"

CN_ADDRESS_PATTERN = re.compile(
    r"([一-龥]{2,}(?:省|自治区|市)[一-龥]{1,}(?:市|区|县)[一-龥0-9号弄巷路街道小区院楼室\-]{2,})"
)
CN_DISEASE_CODE_PATTERN = re.compile(r"\b([A-Z]\d{2}(?:\.\d{1,2})?|[A-Z]{2}\d{2}(?:\.\d{1,2})?)\b")
CN_DRUG_CODE_PATTERN = re.compile(r"\b(国药准字[HZSJBTFC]\d{8})\b", re.I)

ADDRESS_CONTEXT = ("住址", "地址", "籍贯", "现住", "家庭住址")
DISEASE_CONTEXT = ("诊断", "疾病", "ICD", "病种", "出院诊断", "入院诊断")
DRUG_CONTEXT = ("药品", "处方", "国药准字", "用药", "医嘱")


def _has_context(text: str, start: int, keywords: tuple[str, ...], window: int = 24) -> bool:
    snippet = text[max(0, start - window) : start + window]
    return any(keyword in snippet for keyword in keywords)


def _metadata(kind: str) -> dict[str, str]:
    return {"recognizer": kind, "source": "medharness-cn-medical-context"}


class CNAddressRecognizer(PatternRecognizer):
    """Recognizer for Chinese addresses, requiring address-like context."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_ADDRESS_ENTITY,
            patterns=[Pattern(name="cn_address", regex=CN_ADDRESS_PATTERN.pattern, score=0.74)],
            context=list(ADDRESS_CONTEXT),
            supported_language="zh",
            name="medharness_cn_address",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_ADDRESS_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.82,
                recognition_metadata=_metadata("cn_address"),
            )
            for match in CN_ADDRESS_PATTERN.finditer(text)
            if CN_ADDRESS_ENTITY in entities
            and classify_placeholder(match.group(1)) is None
            and _has_context(text, match.start(1), ADDRESS_CONTEXT)
        ]


class CNDiseaseCodeRecognizer(PatternRecognizer):
    """Recognizer for ICD-10/11-like disease codes with clinical context guard."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_DISEASE_CODE_ENTITY,
            patterns=[
                Pattern(name="cn_disease_code", regex=CN_DISEASE_CODE_PATTERN.pattern, score=0.68)
            ],
            context=list(DISEASE_CONTEXT),
            supported_language="zh",
            name="medharness_cn_disease_code",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_DISEASE_CODE_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.8,
                recognition_metadata=_metadata("cn_disease_code"),
            )
            for match in CN_DISEASE_CODE_PATTERN.finditer(text)
            if CN_DISEASE_CODE_ENTITY in entities
            and classify_placeholder(match.group(1)) is None
            and _has_context(text, match.start(1), DISEASE_CONTEXT)
        ]


class CNDrugCodeRecognizer(PatternRecognizer):
    """Recognizer for Chinese drug approval numbers with medication context guard."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_DRUG_CODE_ENTITY,
            patterns=[Pattern(name="cn_drug_code", regex=CN_DRUG_CODE_PATTERN.pattern, score=0.72)],
            context=list(DRUG_CONTEXT),
            supported_language="zh",
            name="medharness_cn_drug_code",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_DRUG_CODE_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.84,
                recognition_metadata=_metadata("cn_drug_code"),
            )
            for match in CN_DRUG_CODE_PATTERN.finditer(text)
            if CN_DRUG_CODE_ENTITY in entities
            and classify_placeholder(match.group(1)) is None
            and _has_context(text, match.start(1), DRUG_CONTEXT)
        ]
