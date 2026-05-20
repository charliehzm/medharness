---
name: tdd-alignment
description: >
  Use this skill at SOP Step 2 to verify and align a Technical Design Document
  (TDD) with the final PRD: checks every PRD-stated acceptance criterion has a
  corresponding test/verification approach, every named stage in PRD has a TDD
  validation strategy, and every L3/L4 data field has a desensitization /
  audit step planned. Produces an alignment report and inserts patches into
  TDD where gaps exist. Chinese trigger examples: "TDD 对齐", "TDD 验收对齐",
  "测试设计对齐 PRD", "Step 2". Do NOT use for unit-test writing (use during
  Step 9), code-level design review (Step 8), or when TDD is missing entirely
  (escalate to author). Success = TDD covers 100% of PRD acceptance criteria
  with named test strategies; PHI handling addressed; staging tests defined.
compatibility: Requires PRD + TDD file read; writes alignment report.
metadata:
  version: "1.0"
  owner: "qa-lead"
  category: "spec"
  maturity: "production"
  sop_step: 2
  hard_gate: false
  outputs: "openspec/changes/<slug>/TDD_ALIGNMENT.md + TDD.md (patched)"
---

# TDD Alignment (Step 2)

## Core mental model
The TDD is the bridge between *what* (PRD) and *how-to-test* (later steps). Misalignment here propagates downstream: an acceptance criterion with no test design becomes an acceptance criterion with no test, becomes a feature shipped without proof.

## What it produces
`TDD_ALIGNMENT.md` with:
- Coverage table: each PRD acceptance criterion → TDD test strategy
- PHI handling table: each L3/L4 field → desensitization step in TDD
- Stage validation table: each PRD stage → TDD's stage-level test plan
- Gaps list (sorted by severity)

## Active context bundle
**Always load first**
1. This `SKILL.md`
2. Final PRD
3. Submitted TDD
4. `COMPLIANCE_TAG.md` (PHI field list)

**Load on demand**
- `reference/test-strategy-catalog.md` (unit / integration / e2e / chaos / compliance / replay)

## Workflow
1. Extract PRD acceptance criteria into a flat list (numbered).
2. For each criterion, find the TDD section that addresses it; record (criterion → tdd-section + test-strategy).
3. Any criterion without a target → gap.
4. For every L3/L4 field in COMPLIANCE_TAG, locate desensitization plan in TDD; missing → gap.
5. For every PRD stage, locate the corresponding TDD stage validation; missing → gap.
6. Emit report; if gaps exist, suggest concrete TDD patches.

## Hard gate checklist
- [ ] 100% of PRD criteria covered (no gaps)
- [ ] Every L3/L4 field has desensitization step named in TDD
- [ ] Each PRD stage has corresponding TDD stage validation
- [ ] Test strategy named (not just "we'll test it")

## Common failure modes
1. **"Tests will be written later" handwave**: TDD says "comprehensive testing" without naming approach. Mitigation: require strategy name from `reference/test-strategy-catalog.md`.
2. **Forgotten staging tests**: PRD has 3 stages, TDD only describes final-state tests. Mitigation: per-stage row in alignment table.
3. **PHI assumed handled by infra**: developer assumes desensitize happens "somewhere". Mitigation: explicit row per field.

## Handoff
After PASS, proceed to Step 3 (OpenSpec change creation).
