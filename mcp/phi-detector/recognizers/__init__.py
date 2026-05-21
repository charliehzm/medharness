"""Custom Chinese medical PHI recognizers for phi-detector v3."""

from __future__ import annotations

from pathlib import Path

from .cn_core import CNIdRecognizer, CNMrnRecognizer, CNPhoneRecognizer


def load_cn_recognizers(fields_path: Path | str | None = None) -> list[object]:
    """Return the core CN recognizers.

    ``fields_path`` is accepted now so T1.3 can wire the fields.yml loader without
    changing the public entrypoint.
    """
    _ = fields_path
    return [CNIdRecognizer(), CNPhoneRecognizer(), CNMrnRecognizer()]


__all__ = [
    "CNIdRecognizer",
    "CNMrnRecognizer",
    "CNPhoneRecognizer",
    "load_cn_recognizers",
]
