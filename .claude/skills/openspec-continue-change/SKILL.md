---
name: openspec-continue-change
description: >
  Use this skill at Step 3 (after openspec-new-change) to expand proposal /
  design / specs into implementation-ready content. Iteratively fills out the
  technical approach, data model, contract specs, test strategy, and risk
  table. Stop when the change is "implementation-ready": every spec has
  acceptance criteria, design covers all PRD scope items, and the
  Compliance Design section is fully populated. Chinese trigger examples:
  "继续 OpenSpec", "OpenSpec 续写", "完善 design.md", "specs 填充". Do NOT
  use for task decomposition (next step), do NOT use to write code. Success
  = design.md covers 100% of in-scope PRD items, every spec has acceptance
  criteria, openspec validate passes.
compatibility: Requires file read/write of openspec/changes/<slug>/. Read upstream PRD / TDD / COMPLIANCE_TAG.
metadata:
  version: "1.0"
  owner: "architect-line"
  category: "spec-author"
  maturity: "production"
  sop_step: 3
  hard_gate: false
  outputs: "fully populated openspec/changes/<slug>/{proposal.md,design.md,specs/*.md}"
---

# OpenSpec Continue Change

The "make it implementation-ready" expansion. After `openspec-new-change` scaffolds, this fills.

## Quality bar — when to stop

The change is ready when **every PRD in-scope item maps to ≥ 1 spec row**, and **every spec row has acceptance criteria**.

## Workflow

1. **PRD ↔ Spec mapping** — list every in-scope item in PRD §3; ensure each has a spec id.
2. **Design body** — technical approach for each spec, in design.md:
   - Data model (tables / messages / contracts)
   - API/IPC contracts
   - Component interaction diagram (mermaid acceptable)
   - Failure modes + recovery
   - Performance budgets
3. **Compliance Design** — refine the section seeded in `openspec-new-change`:
   - Mark every L3/L4 field's flow path
   - Specify desensitization points
   - Specify audit log entries this change introduces
4. **Specs** — for each spec row:
   - one-line behavior description
   - acceptance criteria (Given/When/Then or list)
   - test hook (which test type, what data)
5. **Risks** — top 3 risks + mitigation (in design.md)
6. **Validate** — run `openspec validate` (or `openspec-ff-change` for fast path) — must pass.

## Common failure modes

1. **PRD item without spec** — silent drop. Mitigation: explicit PRD↔Spec matrix at the top of design.md.
2. **Acceptance criteria as wishes** — "the system should be fast". Mitigation: "P99 < 200ms on stage-mock data".
3. **Compliance afterthought** — fill at the end. Mitigation: refine section every time you add a data-touching spec.
4. **Premature implementation** — code samples in design.md > 30 lines. Mitigation: design says what, code says how (later).
