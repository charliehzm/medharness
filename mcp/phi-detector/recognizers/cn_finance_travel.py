"""Finance and travel CN recognizers for phi-detector v3.

>>> is_valid_luhn("6222021234567894")
True
>>> is_valid_cn_bank("6222021234567890")
False
>>> CNBankRecognizer().analyze("银行卡 6222021234567894", ["CN_BANK"], None)[0].entity_type
'CN_BANK'
>>> CNPassportRecognizer().analyze("护照 E12345678", ["CN_PASSPORT"], None)[0].entity_type
'CN_PASSPORT'
>>> CNHKIDRecognizer().analyze("HKID A123456(3)", ["CN_HK_ID"], None)[0].entity_type
'CN_HK_ID'
"""

from __future__ import annotations

import re

try:
    from .cn_core import Pattern, PatternRecognizer, RecognizerResult, classify_placeholder
except ImportError:  # pragma: no cover - direct doctest execution
    from cn_core import Pattern, PatternRecognizer, RecognizerResult, classify_placeholder

CN_BANK_ENTITY = "CN_BANK"
CN_PASSPORT_ENTITY = "CN_PASSPORT"
CN_HK_ID_ENTITY = "CN_HK_ID"
CN_DRIVERS_LICENSE_ENTITY = "CN_DRIVERS_LICENSE"

CN_BANK_PATTERN = re.compile(r"(?<!\d)(\d{16,19})(?!\d)")
CN_PASSPORT_PATTERN = re.compile(r"\b(E\d{8})\b", re.I)
CN_HK_ID_PATTERN = re.compile(r"\b([A-Z]{1,2}\d{6}\(?[0-9A]\)?)\b", re.I)
CN_DRIVERS_LICENSE_PATTERN = re.compile(
    r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
)

CN_BANK_BIN_PREFIXES = {
    "102",
    "103",
    "301",
    "302",
    "303",
    "304",
    "305",
    "306",
    "307",
    "308",
    "309",
    "310",
    "403",
    "421",
    "433",
    "434",
    "436",
    "438",
    "451",
    "458",
    "520",
    "524",
    "552",
    "601",
    "602",
    "603",
    "620",
    "621",
    "622",
    "623",
    "624",
    "625",
    "626",
    "627",
    "628",
    "629",
    "955",
}


def is_valid_luhn(value: str) -> bool:
    """Return True when ``value`` passes Luhn checksum."""
    digits = [int(ch) for ch in value if ch.isdigit()]
    if len(digits) != len(value.strip()):
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def is_known_cn_bank_bin(value: str) -> bool:
    """Check coarse China UnionPay / major-bank BIN prefixes."""
    normalized = value.strip()
    return any(normalized.startswith(prefix) for prefix in CN_BANK_BIN_PREFIXES)


def is_valid_cn_bank(value: str) -> bool:
    normalized = value.strip()
    return (
        classify_placeholder(normalized) is None
        and CN_BANK_PATTERN.fullmatch(normalized) is not None
        and is_known_cn_bank_bin(normalized)
        and is_valid_luhn(normalized)
    )


def _metadata(kind: str) -> dict[str, str]:
    return {"recognizer": kind, "source": "medharness-cn-finance-travel"}


class CNBankRecognizer(PatternRecognizer):
    """Recognizer for China bank cards with BIN and Luhn validation."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_BANK_ENTITY,
            patterns=[Pattern(name="cn_bank", regex=CN_BANK_PATTERN.pattern, score=0.78)],
            context=["银行卡", "卡号", "账号", "银联", "信用卡"],
            supported_language="zh",
            name="medharness_cn_bank",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_BANK_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.91,
                recognition_metadata=_metadata("cn_bank"),
            )
            for match in CN_BANK_PATTERN.finditer(text)
            if CN_BANK_ENTITY in entities and is_valid_cn_bank(match.group(1))
        ]


class CNPassportRecognizer(PatternRecognizer):
    """Recognizer for common PRC passport numbers."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_PASSPORT_ENTITY,
            patterns=[Pattern(name="cn_passport", regex=CN_PASSPORT_PATTERN.pattern, score=0.78)],
            context=["护照", "passport"],
            supported_language="zh",
            name="medharness_cn_passport",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_PASSPORT_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.86,
                recognition_metadata=_metadata("cn_passport"),
            )
            for match in CN_PASSPORT_PATTERN.finditer(text)
            if CN_PASSPORT_ENTITY in entities and classify_placeholder(match.group(1)) is None
        ]


class CNHKIDRecognizer(PatternRecognizer):
    """Recognizer for Hong Kong identity card formats."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_HK_ID_ENTITY,
            patterns=[Pattern(name="cn_hk_id", regex=CN_HK_ID_PATTERN.pattern, score=0.78)],
            context=["香港身份证", "HKID"],
            supported_language="zh",
            name="medharness_cn_hk_id",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult(
                entity_type=CN_HK_ID_ENTITY,
                start=match.start(1),
                end=match.end(1),
                score=0.84,
                recognition_metadata=_metadata("cn_hk_id"),
            )
            for match in CN_HK_ID_PATTERN.finditer(text)
            if CN_HK_ID_ENTITY in entities and classify_placeholder(match.group(1)) is None
        ]


class CNDriversLicenseRecognizer(PatternRecognizer):
    """Recognizer for CN driver license numbers, guarded by local context."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=CN_DRIVERS_LICENSE_ENTITY,
            patterns=[
                Pattern(
                    name="cn_drivers_license",
                    regex=CN_DRIVERS_LICENSE_PATTERN.pattern,
                    score=0.75,
                )
            ],
            context=["驾驶证", "驾照"],
            supported_language="zh",
            name="medharness_cn_drivers_license",
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: object | None = None,
    ) -> list[RecognizerResult]:
        results: list[RecognizerResult] = []
        if CN_DRIVERS_LICENSE_ENTITY not in entities:
            return results
        for match in CN_DRIVERS_LICENSE_PATTERN.finditer(text):
            before = text[max(0, match.start(1) - 20) : match.start(1)]
            if classify_placeholder(match.group(1)) or not any(
                k in before for k in ("驾驶证", "驾照")
            ):
                continue
            results.append(
                RecognizerResult(
                    entity_type=CN_DRIVERS_LICENSE_ENTITY,
                    start=match.start(1),
                    end=match.end(1),
                    score=0.82,
                    recognition_metadata=_metadata("cn_drivers_license"),
                )
            )
        return results
