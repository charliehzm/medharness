"""Strict loader for phi-detector ``fields.yml``.

>>> import tempfile
>>> from pathlib import Path
>>> valid = '''fields:
...   - id: cn_id
...     presidio_entity: CN_ID
...     score_min: 0.6
...     context_boost:
...       keywords: [身份证, ID]
...       window: 20
... '''
>>> path = Path(tempfile.mkdtemp()) / "fields.yml"
>>> _ = path.write_text(valid, encoding="utf-8")
>>> load_fields_yml(path)[0].id
'cn_id'
>>> bad = path.with_name("bad.yml")
>>> _ = bad.write_text("fields:\\n  - id: cn_id\\n", encoding="utf-8")
>>> try:
...     validate_fields_yml(bad)
... except FieldsYmlError as exc:
...     print(type(exc).__name__, exc)
FieldsYmlError bad.yml:2: missing required key 'presidio_entity' at field index 0
>>> dup = path.with_name("dup.yml")
>>> _ = dup.write_text(valid + valid.split("\\n", 1)[1], encoding="utf-8")
>>> try:
...     validate_fields_yml(dup)
... except FieldsYmlError as exc:
...     print(type(exc).__name__, exc)
FieldsYmlError dup.yml:8: duplicate field id 'cn_id'
>>> score = path.with_name("score.yml")
>>> _ = score.write_text(valid.replace("score_min: 0.6", "score_min: 1.2"), encoding="utf-8")
>>> try:
...     validate_fields_yml(score)
... except FieldsYmlError as exc:
...     print(type(exc).__name__, exc)
FieldsYmlError score.yml:4: score_min must be between 0 and 1 at field index 0
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = ("id", "presidio_entity", "score_min", "context_boost")
CONTEXT_REQUIRED_KEYS = ("keywords", "window")


class FieldsYmlError(ValueError):
    """Raised when fields.yml violates the strict schema."""


@dataclass(frozen=True)
class ContextBoost:
    keywords: tuple[str, ...]
    window: int


@dataclass(frozen=True)
class FieldSpec:
    id: str
    presidio_entity: str
    score_min: float
    context_boost: ContextBoost
    pattern: str | None = None
    must_pass_luhn: bool = False
    notes: str | None = None


def load_fields_yml(path: Path | str) -> list[FieldSpec]:
    """Parse and validate ``fields.yml``."""
    return validate_fields_yml(path)


def validate_fields_yml(path: Path | str) -> list[FieldSpec]:
    """Validate ``fields.yml`` and return immutable field specs."""
    source = Path(path)
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise _error(source, 1, "top-level document must be a mapping")
    fields = raw.get("fields")
    if not isinstance(fields, list):
        raise _error(
            source, _line_for_key(source, "fields"), "missing required top-level key 'fields'"
        )

    specs: list[FieldSpec] = []
    seen: dict[str, int] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise _error(
                source, _line_for_field(source, index), f"field index {index} must be a mapping"
            )
        for key in REQUIRED_KEYS:
            if key not in field:
                raise _error(
                    source,
                    _line_for_field(source, index),
                    f"missing required key '{key}' at field index {index}",
                )
        field_id = _string_value(source, field, "id", index)
        if field_id in seen:
            raise _error(source, _line_for_field(source, index), f"duplicate field id '{field_id}'")
        seen[field_id] = index
        score_min = _score_min(source, field, index)
        specs.append(
            FieldSpec(
                id=field_id,
                presidio_entity=_string_value(source, field, "presidio_entity", index),
                score_min=score_min,
                context_boost=_context_boost(source, field["context_boost"], index),
                pattern=_optional_string(source, field, "pattern", index),
                must_pass_luhn=bool(field.get("must_pass_luhn", False)),
                notes=_optional_string(source, field, "notes", index),
            )
        )
    return specs


def _context_boost(source: Path, value: Any, index: int) -> ContextBoost:
    if not isinstance(value, dict):
        raise _error(
            source,
            _line_for_field(source, index),
            f"context_boost must be mapping at field index {index}",
        )
    for key in CONTEXT_REQUIRED_KEYS:
        if key not in value:
            raise _error(
                source,
                _line_for_field(source, index),
                f"missing required key 'context_boost.{key}' at field index {index}",
            )
    keywords = value["keywords"]
    if (
        not isinstance(keywords, list)
        or not keywords
        or not all(isinstance(k, str) and k for k in keywords)
    ):
        raise _error(
            source,
            _line_for_field(source, index),
            f"context_boost.keywords must be non-empty strings at field index {index}",
        )
    window = value["window"]
    if not isinstance(window, int) or window <= 0:
        raise _error(
            source,
            _line_for_field(source, index),
            f"context_boost.window must be positive integer at field index {index}",
        )
    return ContextBoost(keywords=tuple(keywords), window=window)


def _string_value(source: Path, field: dict[str, Any], key: str, index: int) -> str:
    value = field[key]
    if not isinstance(value, str) or not value:
        raise _error(
            source,
            _line_for_field(source, index),
            f"{key} must be non-empty string at field index {index}",
        )
    return value


def _optional_string(source: Path, field: dict[str, Any], key: str, index: int) -> str | None:
    value = field.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise _error(
            source,
            _line_for_field(source, index),
            f"{key} must be non-empty string at field index {index}",
        )
    return value


def _score_min(source: Path, field: dict[str, Any], index: int) -> float:
    value = field["score_min"]
    if not isinstance(value, int | float) or not 0 <= float(value) <= 1:
        raise _error(
            source,
            _line_for_key(source, "score_min", occurrence=index + 1),
            f"score_min must be between 0 and 1 at field index {index}",
        )
    return float(value)


def _error(source: Path, line: int, message: str) -> FieldsYmlError:
    return FieldsYmlError(f"{source.name}:{line}: {message}")


def _line_for_field(source: Path, index: int) -> int:
    seen = -1
    for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("  - "):
            seen += 1
            if seen == index:
                return line_no
    return 1


def _line_for_key(source: Path, key: str, occurrence: int = 1) -> int:
    hits = 0
    for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith(f"{key}:"):
            hits += 1
            if hits == occurrence:
                return line_no
    return 1
