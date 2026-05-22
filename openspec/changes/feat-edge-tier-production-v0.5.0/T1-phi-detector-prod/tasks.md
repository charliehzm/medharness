# T1 · phi-detector v3 production · leaf task plan

> Parent task group: `T1 · phi-detector v3 真集成 Presidio`
> Parent spec: `../specs/T1-phi-detector-prod.spec.md`
> Branch model: each leaf starts from `main` as `feat/T1.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 files. If a leaf needs 3 files, stop and ask maintainer; 4+ files must be split.
- All fixtures are L1 synthetic only. No real PHI may enter git, prompts, logs, tests, or release assets.
- The detector response must not return raw matched text; return offsets, type, score, and `text_sha256`.
- T1 is not complete until `tools/phi_fingerprint_check.py` exists and passes on all red-team fixtures.
- T1 is not complete until recall >= 92%, FP <= 15%, and `python tests/red-team-drills/check_recall.py --min 0.92` passes.

## Leaf Sub-tasks

### T1.1 · recognizer base and CN ID / phone / MRN ✅

- Branch: `feat/T1.1-recognizer-base`
- PR: [#16](https://github.com/charliehzm/medharness/pull/16)
- Merge commit: `f6481d8`
- Leaf commit: `12dd405`
- Files:
  - `mcp/phi-detector/recognizers/__init__.py`
  - `mcp/phi-detector/recognizers/cn_core.py`
- Scope:
  - Add shared recognizer loading API: `load_cn_recognizers(fields_path: Path | str | None = None)`.
  - Implement base helpers for regex recognizers, span normalization, and deterministic SHA-256 helpers if needed by recognizers.
  - Implement `CN_ID`, `CN_PHONE`, and `CN_MRN` recognizers with CN ID checksum and phone prefix validation.
- Acceptance:
  - Recognizers can be imported without loading the full MCP server.
  - Unit-level smoke via `python -m compileall mcp/phi-detector/recognizers`.
  - No raw PHI appears outside synthetic examples embedded in tests or docs.
- Result: completed and merged. CN ID checksum, phone prefix validation, MRN base recognizer, placeholder handling, and loader entry point are available.

### T1.2 · remaining CN custom recognizers ✅

- Branch: `feat/T1.2-cn-recognizers`
- PR: [#18](https://github.com/charliehzm/medharness/pull/18)
- Merge commit: `5025daf`
- Leaf commit: `38d0a90`
- Files:
  - `mcp/phi-detector/recognizers/cn_finance_travel.py`
  - `mcp/phi-detector/recognizers/cn_medical_context.py`
- Scope:
  - Implement `CN_BANK`, `CN_ADDRESS`, `CN_PASSPORT`, `CN_HK_ID`, `CN_DRIVERS_LICENSE`, `CN_DISEASE_CODE`, and `CN_DRUG_CODE`.
  - Add Luhn and known BIN prefix checks for bank cards.
  - Keep ICD / drug-code patterns context-aware to reduce numeric false positives.
- Acceptance:
  - Recognizers are exposed through `load_cn_recognizers`.
  - CN bank invalid Luhn examples are demoted or ignored.
  - No network or cloud calls.
- Result: completed and merged. Finance, travel, address, disease-code, and drug-code recognizers are registered through the CN loader.

### T1.3 · fields.yml with 31 PHI field definitions ✅

- Branch: `feat/T1.3-fields-yml`
- PR: [#19](https://github.com/charliehzm/medharness/pull/19)
- Merge commit: `659150c`
- Leaf commit: `c7fbcf4`
- Files:
  - `mcp/phi-detector/fields.yml`
  - `mcp/phi-detector/recognizers/fields_loader.py`
- Scope:
  - Add the 31-field schema required by the parent spec.
  - Implement strict loader validation for required keys, entity uniqueness, score ranges, and context window defaults.
  - Map each field to a Presidio entity name and local recognizer id.
- Acceptance:
  - Loader rejects malformed fields with actionable errors.
  - All 31 fields load successfully.
  - `fields.yml` contains only generic synthetic patterns and no customer-specific configuration.
- Result: completed and merged. The strict loader validates the 31-field contract used by T1.5 and later packaging work.

### T1.4 · context post-processing rules ✅

- Branch: `feat/T1.4-context-postprocess`
- PR: [#20](https://github.com/charliehzm/medharness/pull/20)
- Merge commit: `9f81e2f`
- Leaf commit: `1621e5f`
- Files:
  - `mcp/phi-detector/postprocess.py`
  - `tests/test_phi_detector_postprocess.py`
- Scope:
  - Implement the 6 required rules: Luhn check, placeholder suppression, log timestamp demotion, name-proximity weighting, 60s cache contract helpers, and CN-Bank strictness.
  - Keep post-processing pure and testable without Presidio runtime where possible.
- Acceptance:
  - Unit tests cover each of the 6 rules.
  - Placeholder hits are suppressed.
  - Log timestamps and hash-like strings are demoted without deleting unrelated PHI detections.
- Result: completed and merged. Span dedup and context rules are applied by the v3 server integration.

### T1.5 · server_v3 Presidio integration ✅

- Branch: `feat/T1.5-presidio-server`
- PR: [#22](https://github.com/charliehzm/medharness/pull/22)
- Merge commit: `5fd5815`
- Leaf commit: `5349589`
- Files:
  - `mcp/phi-detector/server_v3.py`
  - `tests/test_phi_detector_server_v3.py`
- Scope:
  - Replace the current rule-only v3 path with `AnalyzerEngine` based detection.
  - Register all custom CN recognizers from `load_cn_recognizers`.
  - Preserve CLI and stdio compatibility while adding the new output envelope: `{"spans": [...], "stats": {...}}`.
  - Ensure matched raw text is never returned; include `text_sha256` only.
- Acceptance:
  - Health and `detect` CLI still work.
  - Empty input returns no spans.
  - Synthetic CN ID / phone / MRN / name examples produce expected span types.
- Result: completed and merged. Presidio-backed runtime returns `spans` / `stats` envelope with no raw matched text; `CN_NAME` remains graceful-skip forward declaration.

### T1.6 · drill 1 contract and recall gate update ✅

- Branch: `feat/T1.6-recall-drill-contract`
- PR: [#23](https://github.com/charliehzm/medharness/pull/23)
- Merge commit: `7ea24ff`
- Leaf commit: `4b3a29a`
- Files:
  - `tests/red-team-drills/drill_phi_recall.py`
  - `tests/red-team-drills/check_recall.py`
- Scope:
  - Update drill 1 to consume the new `spans` envelope while remaining compatible with legacy `hits` during transition.
  - Report recall, false-positive rate, entity coverage, and failed case ids.
  - Make `check_recall.py --min 0.92` enforce the new recall metric and fail on missing output.
- Acceptance:
  - Current small fixture still runs.
  - A detector returning raw text is treated as a contract violation if observable in output.
  - Drill output includes enough detail for CI artifact review without exposing raw PHI beyond synthetic fixture text.
- Result: completed and merged. Recall gate enforces `--min 0.92`, failed case ids, and raw-text contract violations.

### T1.7 · synthetic corpus expansion ✅

- Branch: `feat/T1.7-synthetic-corpus`
- PR: [#24](https://github.com/charliehzm/medharness/pull/24)
- Merge commit: `141081a`
- Leaf commit: `7e2a47a`
- Files:
  - `tests/red-team-drills/fixtures/synthetic_phi_corpus.jsonl`
  - `tests/red-team-drills/fixtures/synthetic_phi_negative_corpus.jsonl`
- Scope:
  - Expand positive corpus to >= 200 L1 synthetic cases.
  - Add negative corpus with >= 100 L1 synthetic cases covering logs, code snippets, hashes, placeholders, timestamps, docs, and medical non-PHI terms.
  - Cover 10 CN recognizers with >= 10 positive examples each and negative FP categories where applicable.
- Acceptance:
  - Each fixture line declares `id`, `text`, `expected`, `source: synthetic`, and deterministic generation metadata.
  - No real names, phone numbers, patient identifiers, or customer strings.
  - Fixtures are suitable for release packaging.
- Result: completed and merged. Positive corpus has 220 rows / 250 expected mentions; negative corpus has 110 rows across 11 FP categories.

### T1.8 · synthetic fixture fingerprint checker ✅

- Branch: `feat/T1.8-phi-fingerprint-check`
- PR: [#25](https://github.com/charliehzm/medharness/pull/25)
- Merge commit: `8fc334a`
- Leaf commit: `aa94666`
- Files:
  - `tools/phi_fingerprint_check.py`
  - `tests/test_phi_fingerprint_check.py`
- Scope:
  - Implement the R4 gate referenced by the parent `COMPLIANCE_TAG.md`.
  - Validate JSONL fixtures contain `source: synthetic`, generation metadata, no forbidden customer markers, and stable corpus fingerprints.
  - Provide CLI: `python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl`.
- Acceptance:
  - Synthetic fixtures pass.
  - Missing `source: synthetic` fails.
  - Obvious production/customer marker strings fail.
- Result: completed and merged. R4 fixture metadata / marker / fingerprint CLI passes strict mode on both T1.7 fixtures.

### T1.9 · T1 final verification and audit summary ✅

- Branch: `feat/T1.9-phi-detector-verify`
- PR: assigned by T1.9 verification PR
- Commit: assigned by T1.9 verification PR
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T1-phi-detector-prod/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T1-phi-detector-prod/tasks.md`
- Scope:
  - Record final T1 verification numbers after T1.1-T1.8 are merged.
  - Mark T1 leaf tasks complete with links to PRs, commits, test commands, recall, FP rate, and residual risk.
  - Include R1-R5 self-check and audit replay notes.
- Acceptance:
  - T1 DoD is traceable to commands and artifacts.
  - No code changes in this final verification PR.
  - Maintainer can use the summary for Compliance-Agent review.
- Result: final verification PR documents T1 KPI, commands, R1-R5 self-check, residual risks, and T2 handoff.

## Dependency Order

```text
T1.1 -> T1.2 -> T1.3 -> T1.5 -> T1.6 -> T1.7 -> T1.8 -> T1.9
                 \-> T1.4 -> T1.5
```

## Verification Commands Per Leaf

Run the relevant subset for every leaf, expanding as implementation accumulates:

```bash
ruff check .
ruff format .
pytest tests/
bash dryrun_e2e_v2.sh --ci
bash tests/red-team-drills/run_all.sh
python tests/red-team-drills/check_recall.py --min 0.92
python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl
```

For early leaves before T1.8 exists, record that the fingerprint checker is pending and do not mark T1 complete.

## T1 完成签字

提案人 · charliehzm · 2026-05-21 ✅

Compliance Officer · charliehzm（兼任）· 2026-05-21 ✅

Tech Lead · charliehzm · 2026-05-21 ✅

Reviewer-Agent · Claude Code · 2026-05-21 ✅

T1 phi-detector v3 production · acceptance 100% met · 已可作为 T2 desensitize 的 PHI 检测后端
