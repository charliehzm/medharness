"""Strict loader and hot-reload wrapper for ``MODEL_ALLOWLIST.json``.

>>> import json
>>> import tempfile
>>> from pathlib import Path
>>> root = Path(tempfile.mkdtemp())
>>> vendor_path = root / "vendor_families.yml"
>>> _ = vendor_path.write_text('''schema_version: T3.vendor_families.v1
... families:
...   openai: [gpt-5]
...   alibaba: [qwen-max]
... ''', encoding="utf-8")
>>> allowlist_path = root / "MODEL_ALLOWLIST.json"
>>> _ = allowlist_path.write_text(json.dumps({
...     "schema_version": "T3.allowlist.v1",
...     "policy_version": "change-001",
...     "models": [{
...         "id": "qwen-max",
...         "vendor_family": "alibaba",
...         "deployment": "private://qwen-max",
...         "allowed_agent_roles": ["coder", "compliance"],
...         "allowed_data_levels": ["L1", "L2"],
...         "rate_limit_qps": 10,
...     }]
... }), encoding="utf-8")
>>> allowlist = load_allowlist(allowlist_path, vendor_families_path=vendor_path)
>>> allowlist.lookup("qwen-max").vendor_family
'alibaba'
>>> allowlist.all_models()
['qwen-max']
>>> allowlist.active_policy_version()
'change-001'
>>> bad = root / "bad.json"
>>> _ = bad.write_text(json.dumps({"schema_version": "T3.allowlist.v1", "models": []}), encoding="utf-8")
>>> try:
...     load_allowlist(bad, vendor_families_path=vendor_path)
... except AllowlistError as exc:
...     print(type(exc).__name__, exc)
AllowlistError bad.json:1: missing required top-level key 'policy_version'
>>> invalid = root / "invalid.json"
>>> _ = invalid.write_text(json.dumps({
...     "schema_version": "T3.allowlist.v1",
...     "policy_version": "change-001",
...     "models": [{
...         "id": "qwen-max",
...         "vendor_family": "missing-family",
...         "deployment": "private://qwen-max",
...         "allowed_agent_roles": ["coder"],
...         "allowed_data_levels": ["L1"],
...         "rate_limit_qps": 10,
...     }]
... }), encoding="utf-8")
>>> try:
...     load_allowlist(invalid, vendor_families_path=vendor_path)
... except AllowlistError as exc:
...     print(type(exc).__name__, exc)
AllowlistError invalid.json:1: vendor_family 'missing-family' for model_id 'qwen-max' not declared in vendor_families.yml
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vendor_families import DEFAULT_VENDOR_FAMILIES_PATH, load_vendor_families

DEFAULT_ALLOWLIST_PATH = Path(__file__).with_name("MODEL_ALLOWLIST.json")
ALLOWED_DATA_LEVELS = {"L1", "L2", "L3", "L4"}
LOGGER = logging.getLogger(__name__)


class AllowlistError(ValueError):
    """Raised when ``MODEL_ALLOWLIST.json`` violates the strict schema."""


@dataclass(frozen=True)
class AllowlistEntry:
    id: str
    vendor_family: str
    deployment: str
    allowed_agent_roles: tuple[str, ...]
    allowed_data_levels: tuple[str, ...]
    rate_limit_qps: int


@dataclass(frozen=True)
class Allowlist:
    schema_version: str
    policy_version: str
    entries: tuple[AllowlistEntry, ...]

    def lookup(self, model_id: str) -> AllowlistEntry | None:
        for entry in self.entries:
            if entry.id == model_id:
                return entry
        return None

    def all_models(self) -> list[str]:
        return [entry.id for entry in self.entries]

    def active_policy_version(self) -> str:
        return self.policy_version


@dataclass(frozen=True)
class _AllowlistSnapshot:
    allowlist: Allowlist
    mtime_ns: int
    sha256: str


class HotAllowlist:
    """Fail-safe hot reload wrapper for router runtime use."""

    def __init__(
        self,
        path: Path | str = DEFAULT_ALLOWLIST_PATH,
        *,
        vendor_families_path: Path | str = DEFAULT_VENDOR_FAMILIES_PATH,
    ) -> None:
        self._path = Path(path)
        self._vendor_families_path = Path(vendor_families_path)
        self._snapshot: _AllowlistSnapshot | None = None

    def get_allowlist(self) -> Allowlist:
        current = self._load_if_needed()
        if current is None:
            raise AllowlistError(f"{self._path.name}:1: allowlist has not been loaded")
        return current.allowlist

    def _load_if_needed(self) -> _AllowlistSnapshot | None:
        if not self._path.exists():
            return self._snapshot

        try:
            stat = self._path.stat()
            content = self._path.read_text(encoding="utf-8")
            sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if self._snapshot and (
                self._snapshot.mtime_ns == stat.st_mtime_ns and self._snapshot.sha256 == sha256
            ):
                return self._snapshot

            allowlist = load_allowlist(
                self._path,
                vendor_families_path=self._vendor_families_path,
            )
            self._snapshot = _AllowlistSnapshot(
                allowlist=allowlist,
                mtime_ns=stat.st_mtime_ns,
                sha256=sha256,
            )
            LOGGER.info(
                "allowlist reloaded path=%s policy_version=%s sha256=%s",
                self._path,
                allowlist.active_policy_version(),
                sha256,
            )
            return self._snapshot
        except AllowlistError as exc:
            if self._snapshot is not None:
                LOGGER.warning("allowlist reload failed; keeping last active: %s", exc)
                return self._snapshot
            raise
        except OSError as exc:
            if self._snapshot is not None:
                LOGGER.warning("allowlist reload io failed; keeping last active: %s", exc)
                return self._snapshot
            raise AllowlistError(f"{self._path.name}:1: unable to read allowlist: {exc}") from exc


def load_allowlist(
    path: Path | str = DEFAULT_ALLOWLIST_PATH,
    *,
    vendor_families_path: Path | str = DEFAULT_VENDOR_FAMILIES_PATH,
) -> Allowlist:
    source = Path(path)
    raw = _read_json(source)
    if not isinstance(raw, dict):
        raise _error(source, 1, "top-level document must be a mapping")

    for key in ("schema_version", "policy_version", "models"):
        if key not in raw:
            raise _error(source, 1, f"missing required top-level key '{key}'")

    schema_version = _string_value(
        source, raw["schema_version"], "schema_version must be a non-empty string"
    )
    if schema_version != "T3.allowlist.v1":
        raise _error(source, 1, f"unsupported schema_version '{schema_version}'")

    policy_version = _string_value(
        source, raw["policy_version"], "policy_version must be a non-empty string"
    )
    models = raw["models"]
    if not isinstance(models, list) or not models:
        raise _error(source, 1, "models must be a non-empty list")

    declared_vendor_families = set(load_vendor_families(vendor_families_path).values())
    entries: list[AllowlistEntry] = []
    seen: set[str] = set()

    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise _error(
                source, _model_line(source, index), f"model index {index} must be a mapping"
            )
        for key in (
            "id",
            "vendor_family",
            "deployment",
            "allowed_agent_roles",
            "allowed_data_levels",
            "rate_limit_qps",
        ):
            if key not in model:
                raise _error(
                    source,
                    _model_line(source, index),
                    f"missing required key '{key}' at model index {index}",
                )

        model_id = _string_value(
            source, model["id"], f"id must be non-empty string at model index {index}"
        )
        if model_id in seen:
            raise _error(source, _model_line(source, index), f"duplicate model_id '{model_id}'")
        seen.add(model_id)

        vendor_family = _string_value(
            source,
            model["vendor_family"],
            f"vendor_family must be non-empty string at model index {index}",
        )
        if vendor_family not in declared_vendor_families:
            raise _error(
                source,
                _model_line(source, index),
                f"vendor_family '{vendor_family}' for model_id '{model_id}' not declared in vendor_families.yml",
            )

        deployment = _string_value(
            source,
            model["deployment"],
            f"deployment must be non-empty string at model index {index}",
        )
        allowed_agent_roles = _string_list(
            source,
            model["allowed_agent_roles"],
            f"allowed_agent_roles must be non-empty list of strings at model index {index}",
        )
        allowed_data_levels = _string_list(
            source,
            model["allowed_data_levels"],
            f"allowed_data_levels must be non-empty list of strings at model index {index}",
        )
        invalid_levels = [
            level for level in allowed_data_levels if level not in ALLOWED_DATA_LEVELS
        ]
        if invalid_levels:
            raise _error(
                source,
                _model_line(source, index),
                f"allowed_data_levels contains invalid values {invalid_levels!r} at model index {index}",
            )
        rate_limit_qps = model["rate_limit_qps"]
        if not isinstance(rate_limit_qps, int) or rate_limit_qps <= 0:
            raise _error(
                source,
                _model_line(source, index),
                f"rate_limit_qps must be positive integer at model index {index}",
            )

        entries.append(
            AllowlistEntry(
                id=model_id,
                vendor_family=vendor_family,
                deployment=deployment,
                allowed_agent_roles=tuple(allowed_agent_roles),
                allowed_data_levels=tuple(allowed_data_levels),
                rate_limit_qps=rate_limit_qps,
            )
        )

    return Allowlist(
        schema_version=schema_version, policy_version=policy_version, entries=tuple(entries)
    )


def _read_json(source: Path) -> Any:
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _error(source, 1, f"unable to read allowlist: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise _error(source, exc.lineno, f"invalid JSON: {exc.msg}") from exc


def _string_value(source: Path, value: Any, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(source, 1, message)
    return value


def _string_list(source: Path, value: Any, message: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _error(source, 1, message)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _error(source, 1, message)
        result.append(item)
    return tuple(result)


def _model_line(source: Path, index: int) -> int:
    lines = source.read_text(encoding="utf-8").splitlines()
    hits = -1
    for line_no, line in enumerate(lines, start=1):
        if line.lstrip().startswith("-") or '"id"' in line:
            hits += 1
            if hits == index:
                return line_no
    return 1


def _error(source: Path, line: int, message: str) -> AllowlistError:
    return AllowlistError(f"{source.name}:{line}: {message}")
