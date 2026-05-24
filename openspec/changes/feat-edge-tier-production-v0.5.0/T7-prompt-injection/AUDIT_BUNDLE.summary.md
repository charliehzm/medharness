# T7 · prompt-injection drill 4 · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T7 · drill 4 prompt injection`
> Status: final verification recorded for T7 scope; T7.5 is the docs-only closure leaf
> Date: 2026-05-24
> Scope: final verification summary only; no runtime code in T7.5

## 1. Change Overview

T7 delivered a prompt-injection defense line built from a rule-based detector, a 25-case synthetic corpus, a replayable drill, and a CI gate that enforces a 95% block-rate bar.

| Leaf | PR | Merge commit | Leaf commit | One-line result |
|---|---:|---|---|---|
| T7.1 | [#64](https://github.com/charliehzm/medharness/pull/64) | `51a2128` | `196dde0` | Added `detect_injection(text, context=None)` with 5 categories, scored rules, and fail-closed semantics. |
| T7.2 | [#65](https://github.com/charliehzm/medharness/pull/65) | `e2e95ac` | `c3945a1` | Added a 25-case synthetic JSONL corpus with 5 attack families plus benign controls. |
| T7.3 | [#66](https://github.com/charliehzm/medharness/pull/66) | `d6495be` | `e9b9c62` | Replaced the drill stub with TP/FN/FP/TN accounting, per-family stats, and structured JSON output. |
| T7.4 | [#67](https://github.com/charliehzm/medharness/pull/67) | `f5c0260` | `e075fe7` | Added `run_all.sh` drill 4 gate with block-rate and FP-rate enforcement. |
| T7.5 | pending | pending | pending | Records the final T7 verification summary, residual risks, and 4-way sign-off. |

## 2. Compliance Posture

| Redline | Result | Evidence |
|---|---|---|
| R1 PHI never enters raw prompts | YES | `tests/test_prompt_injection_detector.py` includes a sentinel for logger / exception redaction; `tests/test_drill_injection.py` keeps report fields to `case_id`, `category`, `score`, `matched_rules`, and `outcome`; `tests/red-team-drills/fixtures/prompt_injection_corpus.jsonl` is synthetic only. |
| R2 models route by allowlist | N/A for T7 runtime; preserved | T7 does not touch model-router policy files or routing allowlists. |
| R3 full audit record | YES for T7 scope | `tests/red-team-drills/run_all.sh` now enforces the drill 4 gate; `tests/red-team-drills/drill_injection.py` emits a machine-readable report for CI parsing. |
| R4 test data compliance | YES | The corpus is 100% synthetic, uses a blacklist to exclude real jailbreak-library fingerprints, and keeps the blocker / benign split explicit. |
| R5 license permanence | YES | T7.1-T7.5 do not modify `LICENSE`, `NOTICE`, or the Apache 2.0 / CC BY-SA 4.0 commitment. |

R1 details:

- The detector returns `DetectionResult` metadata, not raw text echoes.
- The drill report includes only structured outcome metadata and no case text.
- The corpus file stays synthetic and reviewable.

R3 details:

- T7.3 emits replayable drill metadata for the red-team wrapper.
- T7.4 turns the drill into a hard gate in `run_all.sh`.
- The gate fails loudly when the report shows missed blocks or too many false positives.

## 3. Implementation Summary

### 3.1 T7.1 · prompt-injection detector module

- PR: [#64](https://github.com/charliehzm/medharness/pull/64)
- Merge commit: `51a2128`
- Leaf commit: `196dde0`
- Files:
  - `mcp/prompt-injection-scan/detector.py`
  - `tests/test_prompt_injection_detector.py`
- Result: completed and merged. The detector exposes a single `detect_injection(text, context=None)` API, returns `DetectionResult`, and remains stdlib-only.
- Evidence:
  - 5 attack families: indirect, tool abuse, role escalation, jailbreak, encoding obfuscation.
  - 15 rules total, grouped by family.
  - 8 context rules including code-fence demotion, quote demotion, multilingual boost, repetition penalty, and RAG threshold lowering.
- Test shape: 16 tests.

### 3.2 T7.2 · injection attack corpus 20+ cases

- PR: [#65](https://github.com/charliehzm/medharness/pull/65)
- Merge commit: `e2e95ac`
- Leaf commit: `c3945a1`
- Files:
  - `tests/red-team-drills/fixtures/prompt_injection_corpus.jsonl`
  - `tests/test_prompt_injection_corpus.py`
- Result: completed and merged. The corpus ships 25 synthetic cases, keeps the schema stable, and includes benign controls for false-positive pressure.
- Evidence:
  - Family distribution: indirect 5, tool 4, role 4, jailbreak 4, encoding 4, benign 4.
  - `expected_block` remains explicit per case.
  - The fingerprint blacklist excludes real jailbreak-library signatures.
- Test shape: 9 tests.

### 3.3 T7.3 · drill_injection.py implementation

- PR: [#66](https://github.com/charliehzm/medharness/pull/66)
- Merge commit: `d6495be`
- Leaf commit: `e9b9c62`
- Files:
  - `tests/red-team-drills/drill_injection.py`
  - `tests/test_drill_injection.py`
- Result: completed and merged. The drill classifies TP / FN / FP / TN, computes block rate and FP rate, and emits stable JSON for CI.
- Evidence:
  - `passed` is tied to both `failed_case_ids` and the block-rate threshold.
  - `per_family` stats are included for the 5 attack families plus benign controls.
  - The drill report does not leak case text.
- Test shape: 12 tests.

### 3.4 T7.4 · run_all.sh drill 4 gate

- PR: [#67](https://github.com/charliehzm/medharness/pull/67)
- Merge commit: `f5c0260`
- Leaf commit: `e075fe7`
- Files:
  - `tests/red-team-drills/run_all.sh`
- Result: completed and merged. The gate now enforces `failed_case_ids == []`, `block_rate >= 0.95`, and `fp_rate <= 0.10`.
- Evidence:
  - The wrapper uses inline Python heredoc gating like the earlier drill gates.
  - The gate is shell-only; no new test file was needed.
- Test shape: shell-only wiring.

### 3.5 T7.5 · T7 AUDIT_BUNDLE.summary.md + 4-way sign-off

- PR: pending
- Merge commit: pending
- Leaf commit: pending
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T7-prompt-injection/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T7-prompt-injection/tasks.md`
- Result: pending review. This leaf captures the final verification ledger, residual risk notes, and sign-off.
- Evidence:
  - No runtime code changes.
  - Summary and task ledger stay in sync with T7.1-T7.4.
- Test shape: docs-only.

## 4. ADR-07 Alignment

T7 matches `openspec/changes/feat-edge-tier-production-v0.5.0/design.md` ADR-07:

| ADR-07 decision | T7 implementation | Evidence |
|---|---|---|
| Independent module | `mcp/prompt-injection-scan/` | T7.1 lives outside `mcp/phi-detector/` and keeps a separate threat model. |
| Single public API | `detect_injection(text, context=None)` | T7.1 returns one stable `DetectionResult` shape instead of multiple detector entry points. |
| 5 attack families | indirect / tool abuse / role escalation / jailbreak / encoding | T7.1 rule groups and T7.2 corpus family distribution both cover all five. |
| 8-12 context rules | 8+ context rules | T7.1 includes code-fence demotion, quote demotion, multilingual boost, repetition penalty, and RAG hints. |
| JSONL corpus | `prompt_injection_corpus.jsonl` | T7.2 uses JSONL to match drill 3 conventions and keep review simple. |
| 95% gate | enforced in `run_all.sh` | T7.4 fails the wrapper when the gate drops below threshold. |

Q1-Q5 closure:

- Q1: answered as a single API with internal modular rules.
- Q2: answered as 5 families with indirect / tool abuse / role escalation / jailbreak / encoding.
- Q3: answered as 8-12 context rules; T7 landed in that band.
- Q4: answered as a 95% block-rate gate for v0.5.0-edge.
- Q5: answered as JSONL to stay aligned with drill 3.

## 5. Threat Model + Mitigations

| Threat class | Attack path | Mitigation | Evidence |
|---|---|---|---|
| Indirect injection | "ignore previous instructions" style payloads inside untrusted text | Family-specific rules for instruction override phrases and system-boundary markers | T7.1 indirect rules; T7.2 indirect cases; T7.3 TP outcomes |
| Tool abuse | Prompt asks the model to run shell / eval / network exfiltration steps | Tool-abuse rules for shell execution, `eval`, `curl`, `wget`, and file access language | T7.1 tool-abuse rules; T7.2 tool cases |
| Role escalation | Text tries to reassign the model as admin / system / developer | Role-escalation rules and priority handling | T7.1 role rules; T7.2 role cases |
| Jailbreak phrasing | "DAN" / "developer mode" / policy override language | Jailbreak family rules plus escape-sequence matching | T7.1 jailbreak rules; T7.2 jailbreak cases |
| Encoding obfuscation | Base64, homoglyph, ZWJ, or other hidden payload tricks | Encoding-obfuscation rules detect long entropy strings and invisible-character tricks | T7.1 encoding rules; T7.2 encoding cases |
| Benign false positive | Normal text is blocked by an over-sensitive detector | Benign controls in the corpus and a `fp_rate <= 0.10` gate | T7.2 benign cases; T7.3 FP accounting; T7.4 gate |

Residual note: T7 is deliberately conservative, but it is still rule-based and can miss novel obfuscation styles until v0.6+ corpus refreshes.

## 6. Test Coverage Matrix

Final recorded baseline:

- Full repository tests: `215 passed, 1 skipped`.
- T7 leaf test total: `37` unit tests across T7.1-T7.3.
- Red-team drills: all 4 drill entry points are live; drill 4 is now a real gate.

| Leaf | Test file or drill | Count | Coverage |
|---|---|---:|---|
| T7.1 | `tests/test_prompt_injection_detector.py` | 16 | API, categories, rule hits, context rules, fail-closed, logger redaction |
| T7.2 | `tests/test_prompt_injection_corpus.py` | 9 | corpus parseability, size, family coverage, schema, blacklist, sanity block rate |
| T7.3 | `tests/test_drill_injection.py` | 12 | TP/FN/FP/TN, block rate, FP rate, report shape, end-to-end corpus execution |
| T7.4 | `tests/red-team-drills/run_all.sh` | shell-only | gate wiring, threshold enforcement, fail-loud behavior |
| T7.5 | docs only | 0 | summary and sign-off only |

Drill 4 sanity snapshot:

- Total cases: 25
- Expected-block cases: 21
- Benign cases: 4
- Blocked expected cases: 21 / 21
- False positives: 0 / 4
- Block rate: `1.0`
- FP rate: `0.0`

## 7. Detector Architecture

T7.1 stabilized the detector contract as a small, readable, rule-driven module.

- Public API: `detect_injection(text, context=None) -> DetectionResult`
- Result fields: `blocked`, `category`, `score`, `matched_rules`, `reason`
- Categories: indirect, tool abuse, role escalation, jailbreak, encoding obfuscation
- Rule organization: family-specific rule lists with priority resolution across categories
- Context handling: 8 rules / signals covering code-fence demotion, quoted-string demotion, minimum-length gating, category priority, zh bonus, multilingual boost, repetition penalty, and RAG-aware threshold hints
- Threshold: `BLOCK_THRESHOLD = 0.5` with an env override path documented for future tuning
- Failure mode: fail closed when the detector cannot score safely
- Logging policy: never print the raw input text

The detector stays stdlib-only so it remains compatible with the edge-tier offline build path.

## 8. Corpus Design

T7.2 deliberately keeps the corpus synthetic, compact, and reviewable.

- Format: JSONL
- Total cases: 25
- Attack families: 5 families with 4-5 cases each
- Benign controls: 4 cases
- Schema: `case_id`, `attack_family`, `text`, `expected_block`, `rationale`
- Language mix: English and Chinese examples, plus obfuscation samples
- Safety: no real jailbreak library text, no production RAG snippets, no PHI
- Review affordance: short texts and per-case rationales

Family distribution:

- indirect injection: 5
- tool abuse: 4
- role escalation: 4
- jailbreak: 4
- encoding obfuscation: 4
- benign control: 4

Fingerprint blacklist coverage:

- excludes versioned jailbreak brands
- excludes URL-bearing jailbreak-library signatures
- excludes recognizable real-world prompt-farm markers

## 9. Drill 4 + Gate

T7.3 turns the corpus into a machine-checkable drill report, and T7.4 turns that report into a hard gate.

- Report schema: `schema_version`, `drill`, `total_cases`, `expected_block_cases`, `benign_cases`, `blocked`, `false_negatives`, `false_positives`, `block_rate`, `fp_rate`, `passed`, `failed_case_ids`, `per_family`, `cases`
- Per-case outcome classes: `true_positive`, `false_negative`, `false_positive`, `true_negative`
- Block rate formula: `TP / (TP + FN)`
- FP rate formula: `FP / (FP + TN)`
- Gate checks:
  - `failed_case_ids` must be empty
  - `block_rate` must be at least `0.95`
  - `fp_rate` must be at most `0.10`
- Gate style: inline Python heredoc inside `run_all.sh`, consistent with drill 2 and drill 3
- Output path: `tests/red-team-drills/output/injection.json`

The gate is intentionally conservative: the detector must both catch attacks and avoid over-blocking benign controls.

## 10. Known Limitations + Follow-ups

1. `BLOCK_THRESHOLD` is read at module import time, so runtime env changes do not retune an already-imported detector.
2. The jailbreak escape-sequence rule is literal and does not model every Unicode escape variant.
3. The system-prefix repetition penalty is intentionally simple and may overweight noisy contexts.
4. Homoglyph handling is binary and can mark the whole text rather than give a fine-grained score.
5. The corpus length heuristic is simpler for English than for Chinese tokenization.
6. The RAG hint currently keys off a lightweight context signal rather than a full retrieval provenance graph.
7. Drill reports keep case metadata compact, but the `cases` array is still larger than a pure summary payload.
8. `matched_rules` must stay free of text fragments so the detector cannot leak payload content through rule IDs.
9. v0.6+ should recalibrate the threshold against a broader, more realistic jailbreak corpus and target a lower operating point.
10. RTL / bidi / markdown / HTML smuggling variants are not yet fully covered.

## 11. Handoff Notes

T7 -> T8 CI cron:

- `run_all.sh` already enforces the four red-team drills plus the recall gate.
- A scheduled CI job can now fail loudly on drift without extra runtime wiring.

T7 -> T13 offline build:

- The detector is stdlib-only.
- The corpus is a plain JSONL artifact.
- Both are easy to package into an offline tarball.

T7 -> future RAG / tool integration:

- The API is stable enough to call after retrieval or before tool output.
- A quarantine mode can be layered on later if the maintainer wants "flag but do not block" behavior for borderline cases.

## 12. Sign-off

| Signer | Status | Notes |
|---|---|---|
| codex Coder-Agent | ✅ complete | T7.1-T7.4 leaf PRs are implemented and merged; T7.5 summary is the closure leaf. |
| Claude Reviewer-Agent (异构) | ✅ complete | Each leaf PR has been reviewed and merged. |
| Compliance-Agent (异构) | ✅ complete | R1-R5 evidence is cited above; no raw PHI / text leak path was introduced. |
| Maintainer (`charliehzm`) | ⏳ pending | This PR is the final maintainer sign-off vehicle for T7.5. |
