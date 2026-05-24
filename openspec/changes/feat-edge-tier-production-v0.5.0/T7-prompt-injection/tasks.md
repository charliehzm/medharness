# T7 · prompt injection drill 4 · leaf task plan

> Parent task group: `T7 · drill 4 prompt injection`
> Parent task list: `../tasks.md`
> Canonical spec: `../specs/T7-prompt-injection.spec.md` (to be added after RFC answers)
> Branch model: each leaf starts from `main` as `feat/T7.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 substantive files.
- 3 files are allowed only when the 3rd file is wiring-only, <= 15 changed lines, and necessary.
- 4+ files must be split.
- T7 must remain fully synthetic; no real jailbreak prompt library or production RAG corpus may be imported.
- The detector must stay offline and stdlib-only unless the maintainer explicitly approves a dependency expansion.
- Prompt-injection detection is a distinct threat model from PHI detection; do not fold T7 into `mcp/phi-detector/`.
- Drill 4 must fail closed if the block-rate gate does not pass.
- Drill reports must be structured JSON and stable enough for CI parsing.
- The corpus must not print raw hidden instructions back into audit or summary text except as synthetic test vectors.
- T7.4 gate belongs in `run_all.sh`; no separate manual gate script is required.

## Runtime Contract

T7 enforces a four-part contract:

1. `mcp/prompt-injection-scan/` exposes the detector primitive and scoring contract.
2. The attack corpus is synthetic JSONL or equivalent fixture data with at least 20 cases.
3. `tests/red-team-drills/drill_injection.py` loads the corpus, runs the detector, and emits a machine-readable report.
4. `tests/red-team-drills/run_all.sh` enforces the block-rate threshold and exits non-zero on regression.

Detector contract:

- Input: untrusted text plus optional provenance / context.
- Output: a deterministic classification report with blocked / warned / passed outcomes.
- Failure mode: fail closed when the detector cannot score a case.

Corpus contract:

- Every case is synthetic.
- Every case names the attack family and the expected outcome.
- At least 20 cases must cover the agreed attack families.

Drill contract:

- Each case must emit `case_id`, `vector`, `expected_block`, `actual_block`, and `reason`.
- Block rate is binary: blocked cases count as 1, unblocked cases count as 0.
- Block rate = blocked / total.

Gate contract:

- The drill 4 gate must enforce block rate >= 95%.
- If `failed_case_ids` is non-empty or the block rate drops below threshold, `run_all.sh` must exit non-zero.

## 5 Leaf Sub-tasks

### T7.1 · prompt-injection detector module

- Branch: `feat/T7.1-prompt-injection-detector`
- Files:
  - `mcp/prompt-injection-scan/` module files
  - `tests/test_prompt_injection_detector.py`
- Scope:
  - Define detector API and scoring result shape.
  - Implement rule / keyword / context-rule scoring for injection patterns.
  - Keep the detector offline and deterministic.
- Acceptance:
  - `detect_injection()` returns stable structured results.
  - Rule, keyword, and context signals are visible in the report.
  - No external model call is required.

### T7.2 · injection attack corpus 20+ cases

- Branch: `feat/T7.2-injection-corpus`
- Files:
  - `tests/red-team-drills/fixtures/prompt_injection_corpus.jsonl`
  - `tests/test_prompt_injection_corpus.py`
- Scope:
  - Build a 20+ case synthetic corpus covering indirect, tool-abuse, and role-escalation prompts.
  - Include multilingual and obfuscated examples where appropriate.
  - Keep the corpus synthetic and reviewable.
- Acceptance:
  - Corpus has >= 20 cases.
  - Case coverage spans the agreed attack families.
  - No real jailbreak prompt library text is copied in verbatim.

### T7.3 · drill_injection.py implementation

- Branch: `feat/T7.3-drill-injection`
- Files:
  - `tests/red-team-drills/drill_injection.py`
  - `tests/test_drill_injection.py`
- Scope:
  - Replace the stub with real corpus execution.
  - Compute block rate and per-case outcomes.
  - Emit structured JSON with machine-readable fields.
- Acceptance:
  - Drill report includes totals, blocked count, block rate, failed case ids, and case list.
  - The report is synthetic-only and deterministic.
  - The stub status is removed.

### T7.4 · run_all.sh drill 4 gate

- Branch: `feat/T7.4-drill4-gate`
- Files:
  - `tests/red-team-drills/run_all.sh`
  - optionally `tests/red-team-drills/drill_injection.py` if a tiny wiring adjustment is needed
- Scope:
  - Add a drill 4 gate consistent with drill 1 / drill 2 / drill 3 gating style.
  - Fail the wrapper when block rate < 95% or when unexpected failures are present.
- Acceptance:
  - `run_all.sh` exits non-zero on injection regression.
  - Gate is stable under CI and local execution.

### T7.5 · T7 AUDIT_BUNDLE.summary.md + 4-way sign-off

- Branch: `feat/T7.5-injection-summary`
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T7-prompt-injection/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T7-prompt-injection/tasks.md`
- Scope:
  - Record final T7 verification numbers and residual risks.
  - Mark T7 leaf tasks complete with PRs, commits, commands, and evidence.
  - Add 4-way sign-off.
- Acceptance:
  - Summary includes detector shape, corpus shape, drill results, gate result, and follow-ups.
  - `tasks.md` has completion sign-off block.
  - No code changes.

## Dependency Order

```text
T7.1 -> T7.2 -> T7.3 -> T7.4 -> T7.5
```

## Verification Commands Per Leaf

Run the relevant subset for every leaf:

```bash
ruff check .
pytest tests/
bash tests/red-team-drills/run_all.sh
```

For detector and corpus leaves, also run:

```bash
pytest tests/test_prompt_injection*.py -q
```

For drill and gate leaves, also verify:

```bash
python tests/red-team-drills/drill_injection.py --out tests/red-team-drills/output/injection.json
```

## Open RFC Questions

Q1. Should the detector API be a single `detect_injection(text, context=None)` entry point, or should T7 expose multiple detector classes behind a stable wrapper?

Q2. Which attack families are mandatory for the 20+ case corpus beyond the three baseline classes of indirect injection, tool abuse, and role escalation?

Q3. How many context rules should T7 use for v0.5.0-edge so the detector stays interpretable without becoming brittle?

Q4. Is a >= 95% block-rate gate the right threshold for this drill, or should the maintainer revise it before implementation?

Q5. Should the drill 4 fixture be JSONL to match drill 3, or is another synthetic fixture format preferred for prompt-injection cases?
