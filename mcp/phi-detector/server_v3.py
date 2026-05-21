#!/usr/bin/env python3
"""mcp-phi-detector v3 · Presidio-backed detector.

The v3 contract returns only offsets, entity types, scores, and SHA-256 hashes
of matched substrings. Raw matched text must never leave this process.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
FIELDS_PATH = BASE_DIR / "fields.yml"
MAX_TEXT_CHARS = 8192
DEFAULT_LANGUAGE = "zh"
DEFAULT_SCORE_THRESHOLD = 0.6

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from postprocess import Span, apply_context_rules  # noqa: E402
from recognizers import load_cn_recognizers  # noqa: E402
from recognizers.fields_loader import FieldSpec, load_fields_yml  # noqa: E402

logger = logging.getLogger("medharness.phi_detector.server_v3")


class NoOpContextAwareEnhancer:
    """Disable Presidio lemma context enhancement for regex-only fallback paths."""

    def enhance_using_context(
        self,
        text: str,
        raw_results: list[Any],
        nlp_artifacts: Any,
        recognizers: list[Any],
        context: list[str] | None = None,
    ) -> list[Any]:
        del text, nlp_artifacts, recognizers, context
        return raw_results


class RegexOnlyNlpEngine:
    """Tiny Presidio NLP engine which never downloads spaCy models."""

    def __init__(self, languages: tuple[str, ...] = ("zh", "en")) -> None:
        self._languages = languages
        self._loaded = False
        self._blank_models: dict[str, Any] = {}

    def load(self) -> None:
        import spacy

        self._blank_models = {
            language: spacy.blank("zh" if language == "zh" else "en")
            for language in self._languages
        }
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded

    def process_text(self, text: str, language: str) -> Any:
        from presidio_analyzer.nlp_engine import NlpArtifacts

        if not self._loaded:
            self.load()
        nlp = self._blank_models.get(language) or self._blank_models[self._languages[0]]
        doc = nlp.make_doc(text)
        return NlpArtifacts(
            entities=[],
            tokens=doc,
            tokens_indices=[token.idx for token in doc],
            lemmas=[token.text for token in doc],
            nlp_engine=self,
            language=language,
        )

    def process_batch(
        self,
        texts: list[str],
        language: str,
        batch_size: int = 1,
        n_process: int = 1,
        **kwargs: Any,
    ) -> Any:
        del batch_size, n_process, kwargs
        for text in texts:
            yield text, self.process_text(text, language)

    def is_stopword(self, word: str, language: str) -> bool:
        del word, language
        return False

    def is_punct(self, word: str, language: str) -> bool:
        del language
        return len(word) == 1 and not word.isalnum()

    def get_supported_entities(self) -> list[str]:
        return []

    def get_supported_languages(self) -> list[str]:
        return list(self._languages)


@dataclass(frozen=True)
class DetectorRuntime:
    analyzer: Any | None
    recognizers: list[Any]
    fields: list[FieldSpec]
    entities_by_language: dict[str, list[str]]
    registered_entities: set[str]
    skipped_entities: tuple[str, ...]
    regex_only: bool
    init_warning: str | None = None


_RUNTIME: DetectorRuntime | None = None


def _load_runtime(fields_path: Path = FIELDS_PATH) -> DetectorRuntime:
    fields = load_fields_yml(fields_path)
    recognizers = load_cn_recognizers(fields_path)
    registered_entities = {
        entity
        for recognizer in recognizers
        for entity in getattr(recognizer, "supported_entities", [])
    }

    analyzer = None
    regex_only = True
    init_warning = _spacy_model_warning()
    try:
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry

        registry = RecognizerRegistry(supported_languages=["zh", "en"])
        nlp_engine = RegexOnlyNlpEngine()
        nlp_engine.load()
        registry.load_predefined_recognizers(languages=["en"], nlp_engine=nlp_engine)
        for recognizer in recognizers:
            registry.add_recognizer(recognizer)
        registered_entities.update(
            entity
            for recognizer in registry.recognizers
            for entity in getattr(recognizer, "supported_entities", [])
        )
        analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=nlp_engine,
            supported_languages=["zh", "en"],
            context_aware_enhancer=NoOpContextAwareEnhancer(),
        )
        regex_only = bool(init_warning)
    except Exception as exc:  # pragma: no cover - exercised by dependency failure.
        init_warning = f"presidio unavailable; regex-only fallback active: {exc}"
        logger.warning(init_warning)

    skipped_entities = tuple(
        sorted(
            {
                field.presidio_entity
                for field in fields
                if field.presidio_entity not in registered_entities
            }
        )
    )
    if skipped_entities:
        logger.warning("Skipping unregistered fields.yml entities: %s", ", ".join(skipped_entities))

    entities_by_language = {
        "zh": _entities_for_language(fields, registered_entities, language="zh"),
        "en": _entities_for_language(fields, registered_entities, language="en"),
    }
    return DetectorRuntime(
        analyzer=analyzer,
        recognizers=recognizers,
        fields=fields,
        entities_by_language=entities_by_language,
        registered_entities=registered_entities,
        skipped_entities=skipped_entities,
        regex_only=regex_only,
        init_warning=init_warning,
    )


def _runtime() -> DetectorRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = _load_runtime()
    return _RUNTIME


def _spacy_model_warning() -> str | None:
    try:
        import spacy

        if spacy.util.is_package("zh_core_web_sm") or (BASE_DIR / "zh_core_web_sm").exists():
            return None
        raise OSError("zh_core_web_sm is not installed")
    except Exception as exc:
        warning = f"zh_core_web_sm unavailable; regex-only fallback active: {exc}"
        logger.warning(warning)
        return warning
    return None


def _entities_for_language(
    fields: list[FieldSpec],
    registered_entities: set[str],
    language: str,
) -> list[str]:
    entities = [
        field.presidio_entity
        for field in fields
        if field.presidio_entity in registered_entities
        and _entity_language(field.presidio_entity) == language
    ]
    return list(dict.fromkeys(entities))


def _entity_language(entity: str) -> str:
    if entity.startswith("CN_"):
        return "zh"
    return "en"


def _context_keywords(fields: list[FieldSpec], entities: list[str]) -> list[str]:
    allowed = set(entities)
    keywords: list[str] = []
    for field in fields:
        if field.presidio_entity in allowed:
            keywords.extend(field.context_boost.keywords)
    return list(dict.fromkeys(keywords))


def _normalize_language(language: str | None) -> str:
    if language in {"zh", "en"}:
        return language
    return DEFAULT_LANGUAGE


def _normalize_threshold(value: Any) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return DEFAULT_SCORE_THRESHOLD
    return min(max(threshold, 0.0), 1.0)


def _analyze_with_presidio(
    runtime: DetectorRuntime,
    text: str,
    language: str,
    entities: list[str],
    score_threshold: float,
) -> list[Any]:
    if runtime.analyzer is None or not entities:
        return []
    return runtime.analyzer.analyze(
        text=text,
        language=language,
        entities=entities,
        score_threshold=0.0,
        context=_context_keywords(runtime.fields, entities),
        return_decision_process=False,
    )


def _analyze_with_local_recognizers(
    runtime: DetectorRuntime,
    text: str,
    entities: list[str],
) -> list[Any]:
    if not entities:
        return []
    output: list[Any] = []
    for recognizer in runtime.recognizers:
        supported = [
            entity for entity in getattr(recognizer, "supported_entities", []) if entity in entities
        ]
        if supported:
            output.extend(recognizer.analyze(text=text, entities=supported, nlp_artifacts=None))
    return output


def _to_envelope(
    text: str,
    spans: list[Span],
    duration_ms: float,
    runtime: DetectorRuntime | None = None,
) -> dict[str, Any]:
    max_score = max((span.score for span in spans), default=0.0)
    return {
        "spans": [
            {
                "start": span.start,
                "end": span.end,
                "entity_type": span.entity_type,
                "type": span.entity_type,
                "score": round(float(span.score), 6),
                "text_sha256": sha256(text[span.start : span.end].encode("utf-8")).hexdigest(),
            }
            for span in spans
        ],
        "stats": {
            "recall_estimate": round(max_score, 6),
            "duration_ms": round(duration_ms, 3),
        },
        "summary": {
            "total_hits": len(spans),
            "max_confidence": round(max_score, 6),
            "blocking_recommendation": max_score >= 0.9,
        },
        "_meta": {
            "version": "0.5-v3-presidio",
            "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "passes": ["presidio", "context-rules"],
            "skipped_entities": list(runtime.skipped_entities) if runtime else [],
            "regex_only": runtime.regex_only if runtime else False,
        },
    }


def detect_v3(text: str, context: dict | None = None) -> dict[str, Any]:
    """Detect PHI spans and return the v0.5 envelope."""
    started = time.perf_counter()
    context = context or {}
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    text = text[:MAX_TEXT_CHARS]
    if not text:
        return _to_envelope("", [], (time.perf_counter() - started) * 1000)

    runtime = _runtime()
    language = _normalize_language(context.get("language"))
    score_threshold = _normalize_threshold(context.get("score_threshold", DEFAULT_SCORE_THRESHOLD))
    requested_entities = context.get("entities")
    entities = runtime.entities_by_language.get(language, [])
    if isinstance(requested_entities, list):
        requested = {str(entity) for entity in requested_entities}
        entities = [entity for entity in entities if entity in requested]

    try:
        raw = _analyze_with_presidio(runtime, text, language, entities, score_threshold)
    except Exception as exc:
        logger.warning("Presidio analyze failed; using local recognizer fallback: %s", exc)
        raw = _analyze_with_local_recognizers(runtime, text, entities)
    if not raw:
        raw = _analyze_with_local_recognizers(runtime, text, entities)

    spans = apply_context_rules(text, raw, score_threshold)
    duration_ms = (time.perf_counter() - started) * 1000
    return _to_envelope(text, spans, duration_ms, runtime)


def detect(text: str, context: dict | None = None) -> list[dict[str, Any]]:
    """Legacy drill shim returning span dictionaries only."""
    return detect_v3(text, context)["spans"]


def _serve_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method")
        params = req.get("params", {})
        if method == "detect":
            result = detect_v3(params.get("text", ""), params.get("context"))
            resp = {"id": req.get("id"), "result": result}
        elif method == "health":
            runtime = _runtime()
            resp = {
                "id": req.get("id"),
                "result": {
                    "status": "ok-v3",
                    "backend": "presidio",
                    "regex_only": runtime.regex_only,
                    "skipped_entities": list(runtime.skipped_entities),
                    "warning": runtime.init_warning,
                },
            }
        else:
            resp = {"id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "serve" and sys.argv[2] == "--stdio":
        return _serve_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "detect"
    if cmd == "health":
        runtime = _runtime()
        print(
            json.dumps(
                {
                    "status": "ok-v3",
                    "backend": "presidio",
                    "regex_only": runtime.regex_only,
                    "skipped_entities": list(runtime.skipped_entities),
                    "warning": runtime.init_warning,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if cmd == "detect":
        try:
            req = json.load(sys.stdin)
        except Exception:
            req = {}
        text = req.get("text", "") or ""
        context = req.get("context") or {}
        if "language" in req and "language" not in context:
            context["language"] = req["language"]
        if "score_threshold" in req and "score_threshold" not in context:
            context["score_threshold"] = req["score_threshold"]
        if "entities" in req and "entities" not in context:
            context["entities"] = req["entities"]
        print(json.dumps(detect_v3(text, context), ensure_ascii=False))
        return 0
    print(json.dumps({"error": f"unknown cmd: {cmd}"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
