---
name: prd-implementation-precheck
description: >
  Use this skill at Step 1 (PRD pre-check) and Step 2 (TDD alignment) of the
  v2 12-step SOP to find blockers and warnings in PRD / TDD before any
  implementation work begins. Produces a structured gap list pointing to
  missing scope boundaries, undefined acceptance criteria, unresolved
  cross-team dependencies, vague metrics, and stage breakdown gaps.
  Chinese trigger examples: "PRD 预检", "PRD 检查", "TDD 对齐检查",
  "需求文档审查", "PRD 缺口扫描", "Step 1", "Step 2". Do NOT use to write
  the PRD itself (use `prd` Skill), do NOT use as substitute for compliance
  precheck (Step 0 is separate). Success = zero blockers, zero warnings,
  stage breakdown present, every acceptance criterion has a measurable test
  hook, every dependency has a named owner.
compatibility: Requires file read of PRD/TDD. No external services required.
metadata:
  version: "1.0"
  owner: "product-line"
  category: "spec-gate"
  maturity: "production"
  sop_step: "1, 2"
  hard_gate: false
  outputs: "PRD_PRECHECK_REPORT.md (gap list with blocker/warning severity)"
---

# PRD Implementation Precheck

The Step 1 / Step 2 gate. Catches PRD / TDD ambiguity **before** OpenSpec is generated, so we don't have to retrofit later.

## Core mental model

A PRD is implementation-ready when:
- Every feature has a **defined boundary** (in/out of scope, both stated)
- Every acceptance criterion has a **measurable test hook**
- Every cross-team dependency has a **named owner**
- Every metric has a **baseline + target + measurement method**
- The scope is **broken into shippable stages**, each with its own DoD

This skill scans for violations and emits a gap report.

## What this skill produces

`PRD_PRECHECK_REPORT.md` with:
- Blockers (must fix before proceeding)
- Warnings (should fix; can proceed with explicit override)
- Suggestions (informational)

## When NOT to use

- Writing or expanding a PRD (use `prd`)
- Compliance pre-check (use `compliance-precheck` Step 0)
- Architecture review (use Plan agent / openspec-new-change)

## Active context bundle

**Always load first**
1. This `SKILL.md`
2. The target PRD / TDD file
3. `reference/precheck-checklist.md` — 30+ canonical gaps
4. `reference/severity-rubric.md`

## Workflow

1. **Read** PRD / TDD top to bottom.
2. **Run checklist** — for each item, mark present / missing / vague.
3. **Stage breakdown audit** — does the PRD propose a stage 1 / 2 / 3 split? Each stage has its own DoD?
4. **Metric audit** — every KPI has baseline + target + measurement method?
5. **Dependency audit** — every "needs X from team Y" has an owner + due date?
6. **Compose report** — group by severity, point at exact PRD section/line.
7. **Hand off** — if blockers > 0, send back to `prd` Skill; if only warnings, surface to user for explicit accept/fix decision.

## Hard gate / soft gate

Hard for blockers. Warnings can be accepted with sign-off (recorded in report).

## Common failure modes

1. **"Looks complete" trap** — PRD reads fluently but lacks measurable criteria. Mitigation: always demand metric formula, not metric name.
2. **Stage breakdown handwaved** — "Stage 1 MVP, Stage 2 polish" with no scope cut. Mitigation: require feature-level allocation per stage.
3. **Owner = team name** — "Backend team" is not an owner. Mitigation: require named individual + role.
4. **Acceptance via dogfooding** — "users say it's good" is not measurable. Mitigation: require quantitative + qualitative pair.
