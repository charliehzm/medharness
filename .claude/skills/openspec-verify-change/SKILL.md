---
name: openspec-verify-change
description: >
  Use this skill at Step 7 of the v2 SOP to verify that all tasks in the
  active OpenSpec change are implemented and align with their specs.
  Cross-checks tasks.md checkboxes against actual code presence, runs
  per-spec acceptance criteria as smoke tests where possible, and surfaces
  unimplemented artifacts. Verify is a HARD GATE: failure routes back to
  Step 6 (openspec-apply-change) until clear. Chinese trigger examples:
  "OpenSpec verify", "Step 7", "核验变更", "检查未实现工件". Do NOT use to
  judge code quality (that's Step 8 review), do NOT use to verify
  compliance (that's Step 10). Success = every task checked, every spec
  has evidence, unimplemented-artifact list is empty.
compatibility: Requires file read of change directory + code workspace; optional test runner.
metadata:
  version: "1.0"
  owner: "qa-line"
  category: "spec-gate"
  maturity: "production"
  sop_step: 7
  hard_gate: true
  outputs: "openspec/changes/<slug>/VERIFY_REPORT.md"
---

# OpenSpec Verify Change

The "did we actually build what we said" gate.

## What it checks (NOT code quality)

| Check | Pass criterion |
|---|---|
| Tasks checkbox parity | every `[x]` task has a referenced code change in git |
| Spec evidence | every spec id appears in commit messages / file headers / test names |
| Acceptance criteria smoke | per-spec acceptance criteria runnable on stage-mock data, smoke green |
| File scope discipline | no task exceeded 2 files |
| Compliance touchpoints | every L3/L4-touching task's PR mentions `phi-desensitize` use |

## Workflow

1. Parse tasks.md / tasks/*.md → list of completed tasks + intended files.
2. Diff against git log / current workspace → identify gaps.
3. For each gap, mark as one of: missing-file / missing-test / missing-checkbox / scope-overflow.
4. Run acceptance criteria smoke tests for each spec.
5. Emit `VERIFY_REPORT.md` with passes / failures / actions.

## Hard gate

If any failure → return to Step 6, fix, re-run. Do not pass to Step 8.

## Common failure modes

1. **Checkbox theater** — task marked done without code. Mitigation: parity check.
2. **Hidden Steve work** — task touched 4 files. Mitigation: scope discipline check.
3. **Spec without test hook** — acceptance criteria not executable. Mitigation: hand back to `openspec-continue-change` to refine.
