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

### T7.1 · prompt-injection detector module ✅

- Branch: `feat/T7.1-prompt-injection-detector`
- PR: [#64](https://github.com/charliehzm/medharness/pull/64)
- Merge commit: `51a2128`
- Leaf commit: `196dde0`
- Files:
  - `mcp/prompt-injection-scan/detector.py`
  - `tests/test_prompt_injection_detector.py`
- Result: completed and merged. `detect_injection(text, context=None)` now returns `DetectionResult` with 5 categories, scored rule hits, and fail-closed semantics.
- Tests: 16.

### T7.2 · injection attack corpus 20+ cases ✅

- Branch: `feat/T7.2-injection-corpus`
- PR: [#65](https://github.com/charliehzm/medharness/pull/65)
- Merge commit: `e2e95ac`
- Leaf commit: `c3945a1`
- Files:
  - `tests/red-team-drills/fixtures/prompt_injection_corpus.jsonl`
  - `tests/test_prompt_injection_corpus.py`
- Result: completed and merged. The corpus ships 25 synthetic cases with 5 attack families plus benign controls and a fingerprint blacklist.
- Tests: 9.

### T7.3 · drill_injection.py implementation ✅

- Branch: `feat/T7.3-drill-injection`
- PR: [#66](https://github.com/charliehzm/medharness/pull/66)
- Merge commit: `d6495be`
- Leaf commit: `e9b9c62`
- Files:
  - `tests/red-team-drills/drill_injection.py`
  - `tests/test_drill_injection.py`
- Result: completed and merged. The drill computes TP / FN / FP / TN, block rate, FP rate, and per-family stats in stable JSON.
- Tests: 12.

### T7.4 · run_all.sh drill 4 gate ✅

- Branch: `feat/T7.4-drill4-gate`
- PR: [#67](https://github.com/charliehzm/medharness/pull/67)
- Merge commit: `f5c0260`
- Leaf commit: `e075fe7`
- Files:
  - `tests/red-team-drills/run_all.sh`
- Result: completed and merged. The gate enforces `failed_case_ids == []`, `block_rate >= 0.95`, and `fp_rate <= 0.10`.
- Tests: shell-only wiring.

### T7.5 · T7 AUDIT_BUNDLE.summary.md + 4-way sign-off ⏳

- Branch: `feat/T7.5-injection-summary`
- PR: pending
- Merge commit: pending
- Leaf commit: pending
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T7-prompt-injection/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T7-prompt-injection/tasks.md`
- Result: pending review. This leaf records the final T7 verification summary, residual risks, and sign-off.
- Tests: docs only.

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

## Final Verification Snapshot

- `.venv/bin/ruff check .` -> clean.
- Final recorded repository baseline after T7.4: `215 passed, 1 skipped`.
- Drill 4 recorded baseline: `25` cases, `21` expected-block cases, `4` benign cases, `block_rate=1.0`, `fp_rate=0.0`.
- T7 leaf test total: `37` unit tests across T7.1-T7.3.
- T7.4 gate is active in `tests/red-team-drills/run_all.sh`.

## 4-Way Sign-off

| Signer | Status | Notes |
|---|---|---|
| codex Coder-Agent | ✅ complete | T7.1-T7.4 are implemented and merged; T7.5 is the closure leaf. |
| Claude Reviewer-Agent (异构) | ✅ complete | Each leaf PR has already passed review and merge. |
| Compliance-Agent (异构) | ✅ complete | R1-R5 evidence is cited in `AUDIT_BUNDLE.summary.md`; no raw text leak path introduced. |
| Maintainer (`charliehzm`) | ⏳ pending | This PR is the final maintainer sign-off vehicle for T7.5. |
