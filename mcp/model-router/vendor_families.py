"""Strict offline loader for model-router ``vendor_families.yml``.

>>> import tempfile
>>> from pathlib import Path
>>> valid = '''schema_version: T3.vendor_families.v1
... families:
...   openai:
...     - gpt-5
...   anthropic:
...     - claude-sonnet-4.6
... '''
>>> path = Path(tempfile.mkdtemp()) / "vendor_families.yml"
>>> _ = path.write_text(valid, encoding="utf-8")
>>> load_vendor_families(path)["gpt-5"]
'openai'
>>> missing = path.with_name("missing.yml")
>>> _ = missing.write_text("schema_version: T3.vendor_families.v1\\n", encoding="utf-8")
>>> try:
...     load_vendor_families(missing)
... except FamiliesError as exc:
...     print(type(exc).__name__, exc)
FamiliesError missing.yml:1: missing required top-level key 'families'
>>> duplicate = path.with_name("duplicate.yml")
>>> _ = duplicate.write_text('''schema_version: T3.vendor_families.v1
... families:
...   openai:
...     - gpt-5
...   local:
...     - gpt-5
... ''', encoding="utf-8")
>>> try:
...     load_vendor_families(duplicate)
... except FamiliesError as exc:
...     print(type(exc).__name__, exc)
FamiliesError duplicate.yml:6: duplicate model_id 'gpt-5'
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_VENDOR_FAMILIES_PATH = Path(__file__).with_name("vendor_families.yml")
REQUIRED_TOP_LEVEL_KEYS = ("schema_version", "families")


class FamiliesError(ValueError):
    """Raised when the vendor family mapping is missing or invalid."""


@dataclass(frozen=True)
class FamilyEntry:
    """One deterministic ``model_id -> vendor_family`` binding."""

    model_id: str
    vendor_family: str
    line: int


@dataclass(frozen=True)
class VendorFamilyMap:
    """Validated family entries from one vendor family mapping document."""

    source: Path
    schema_version: str
    entries: tuple[FamilyEntry, ...]

    def as_dict(self) -> dict[str, str]:
        """Return the model lookup consumed by model-router policy leaves."""
        return {entry.model_id: entry.vendor_family for entry in self.entries}

    def resolve(self, model_id: str) -> str:
        """Resolve one known model id or fail closed for an unknown model."""
        try:
            return self.as_dict()[model_id]
        except KeyError as exc:
            raise _error(self.source, 1, f"unknown model_id '{model_id}'") from exc


def load_vendor_families(
    path: Path | str = DEFAULT_VENDOR_FAMILIES_PATH,
) -> dict[str, str]:
    """Load and validate the offline vendor family lookup."""
    return load_vendor_family_map(path).as_dict()


def resolve_vendor_family(
    model_id: str,
    path: Path | str = DEFAULT_VENDOR_FAMILIES_PATH,
) -> str:
    """Resolve a model vendor family through the strict offline loader."""
    return load_vendor_family_map(path).resolve(model_id)


def load_vendor_family_map(
    path: Path | str = DEFAULT_VENDOR_FAMILIES_PATH,
) -> VendorFamilyMap:
    """Load a frozen vendor family map from YAML."""
    source = Path(path)
    raw = _read_yaml(source)
    if not isinstance(raw, dict):
        raise _error(source, 1, "top-level document must be a mapping")

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in raw:
            raise _error(
                source,
                _line_for_key(source, key),
                f"missing required top-level key '{key}'",
            )

    extra_keys = set(raw) - set(REQUIRED_TOP_LEVEL_KEYS)
    if extra_keys:
        key = sorted(extra_keys, key=str)[0]
        raise _error(source, _line_for_key(source, str(key)), f"unknown top-level key '{key}'")

    schema_version = _string_value(
        source,
        raw["schema_version"],
        "schema_version must be a non-empty string",
        _line_for_key(source, "schema_version"),
    )
    families = raw["families"]
    if not isinstance(families, dict) or not families:
        raise _error(
            source,
            _line_for_key(source, "families"),
            "families must be a non-empty mapping",
        )

    entries: list[FamilyEntry] = []
    seen: set[str] = set()
    for vendor_family, model_ids in families.items():
        family_line = _line_for_family(source, vendor_family)
        family = _string_value(
            source,
            vendor_family,
            "vendor_family must be a non-empty string",
            family_line,
        )
        if not isinstance(model_ids, list) or not model_ids:
            raise _error(source, family_line, f"family '{family}' must list model_ids")

        for model_id in model_ids:
            occurrence = sum(entry.model_id == model_id for entry in entries) + 1
            model_line = _line_for_model(source, model_id, occurrence, len(entries) + 1)
            model = _string_value(
                source,
                model_id,
                f"model_id in family '{family}' must be a non-empty string",
                model_line,
            )
            if model in seen:
                raise _error(source, model_line, f"duplicate model_id '{model}'")
            seen.add(model)
            entries.append(FamilyEntry(model_id=model, vendor_family=family, line=model_line))

    return VendorFamilyMap(source=source, schema_version=schema_version, entries=tuple(entries))


def _read_yaml(source: Path) -> Any:
    try:
        return yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _error(source, 1, f"unable to read mapping: {exc.strerror or exc}") from exc
    except yaml.YAMLError as exc:
        line = getattr(getattr(exc, "problem_mark", None), "line", 0) + 1
        raise _error(source, line, f"invalid YAML: {exc}") from exc


def _string_value(source: Path, value: Any, message: str, line: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(source, line, message)
    return value


def _error(source: Path, line: int, message: str) -> FamiliesError:
    return FamiliesError(f"{source.name}:{line}: {message}")


def _line_for_key(source: Path, key: str) -> int:
    for line_no, line in enumerate(_source_lines(source), start=1):
        if line.lstrip().startswith(f"{key}:"):
            return line_no
    return 1


def _line_for_family(source: Path, vendor_family: Any) -> int:
    family = str(vendor_family)
    for line_no, line in enumerate(_source_lines(source), start=1):
        if line.startswith("  ") and line.strip().startswith(f"{family}:"):
            return line_no
    return _line_for_key(source, "families")


def _line_for_model(source: Path, model_id: Any, occurrence: int, fallback: int) -> int:
    model = str(model_id)
    hits = 0
    for line_no, line in enumerate(_source_lines(source), start=1):
        stripped = line.strip()
        if stripped.startswith("- ") and stripped.removeprefix("- ").strip("'\"") == model:
            hits += 1
            if hits == occurrence:
                return line_no
    return fallback


def _source_lines(source: Path) -> list[str]:
    try:
        return source.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
