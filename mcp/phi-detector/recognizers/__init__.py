"""Custom Chinese medical PHI recognizers for phi-detector v3."""

from __future__ import annotations

from pathlib import Path

from . import cn_finance_travel as finance
from . import cn_medical_context as medical
from .cn_core import CNIdRecognizer, CNMrnRecognizer, CNPhoneRecognizer


def load_cn_recognizers(fields_path: Path | str | None = None) -> list[object]:
    """Return the core CN recognizers.

    ``fields_path`` is accepted now so T1.3 can wire the fields.yml loader without
    changing the public entrypoint.
    """
    _ = fields_path
    extra = (
        finance.CNBankRecognizer,
        finance.CNPassportRecognizer,
        finance.CNHKIDRecognizer,
        finance.CNDriversLicenseRecognizer,
        medical.CNAddressRecognizer,
        medical.CNDiseaseCodeRecognizer,
        medical.CNDrugCodeRecognizer,
    )
    return [CNIdRecognizer(), CNPhoneRecognizer(), CNMrnRecognizer(), *(cls() for cls in extra)]


__all__ = [
    "CNIdRecognizer",
    "CNMrnRecognizer",
    "CNPhoneRecognizer",
    "load_cn_recognizers",
]
