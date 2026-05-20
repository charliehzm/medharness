---
name: compliance-precheck
description: >
  Use this skill at the very start of every OpenSpec change (Step 0) for a medical-data
  SaaS / data platform repository. It classifies the data tier (L1-L4) the change
  will touch, enumerates the minimal required fields, and produces a signed
  COMPLIANCE_TAG.md plus a MODEL_ALLOWLIST.json that the mcp-model-router uses
  as a runtime gate. Always run before any PRD work, model invocation, or
  code generation that may touch patient / health data. Chinese trigger examples:
  "合规预检", "数据分级", "新需求合规", "字段清单合规", "PHI 风险评估",
  "Step 0", "模型 allowlist 生成". Do NOT use for non-medical changes, for
  pure infra refactors with no data exposure, or after a change has already
  entered Step 1. Success = signed COMPLIANCE_TAG.md, valid MODEL_ALLOWLIST.json
  injected into mcp-model-router, all "Yes" risks have mitigation, zero unsigned
  fields entering the prompt.
compatibility: Requires file read/write + access to mcp-model-router (M2+). Compliance Officer signature is human gate; this skill prepares the artifact but does not bypass signature.
metadata:
  version: "1.0"
  owner: "compliance-committee"
  category: "compliance-gate"
  maturity: "production"
  sop_step: 0
  hard_gate: true
  outputs: "openspec/changes/<slug>/COMPLIANCE_TAG.md openspec/changes/<slug>/MODEL_ALLOWLIST.json"
---

# Compliance Precheck (Step 0)

This skill is the **first gate** of the v2 12-step SOP. Without a signed COMPLIANCE_TAG and an injected MODEL_ALLOWLIST, every downstream step (PRD / TDD / OpenSpec / code / tests / archive) is invalid.

## Core mental model

You are turning **"business desire"** into **"data + model contract"**.

- Business says: "we want to match patients across hospitals by name + DOB"
- Compliance says: "name + DOB are L4 PHI; allowed models = {private deepseek-v4-pro after desensitization}; deny list = {claude opus public, gpt-4 public}; required mitigation = phi-desensitize before any prompt"

Your job: turn the first sentence into the structured second sentence.

## What this skill produces

Two artifacts, both inside the change directory:

1. `openspec/changes/<slug>/COMPLIANCE_TAG.md` — human-readable signed contract (template at [openspec/templates/COMPLIANCE_TAG.md](../../../openspec/templates/COMPLIANCE_TAG.md))
2. `openspec/changes/<slug>/MODEL_ALLOWLIST.json` — machine-readable, injected into mcp-model-router

## When NOT to use this skill

Skip for:
- Pure UI string / i18n changes touching no business data
- Build / CI / docs-only changes (still log it but mark L1)
- Bugfixes inside an existing change that already has a valid COMPLIANCE_TAG (just bump its version)

## Active context bundle

**Always load first**
1. This `SKILL.md`
2. `reference/data-tier-rubric.md` — how to decide L1 vs L2 vs L3 vs L4
3. `reference/field-minimization-protocol.md` — how to challenge field inclusion
4. `openspec/templates/COMPLIANCE_TAG.md` — the canonical template

**Load on demand**
- `reference/regulation-cheatsheet.md` — HIPAA 18 identifiers / PIPL / 健康医疗数据安全指南 mapping (when classifying ambiguous fields)
- `reference/model-deployment-matrix.md` — which model can run where (when filling allowlist)

## Workflow

### Phase 1 · Intake (≤ 5 min)
- Read the business need draft.
- List every data field the change could read / write / log.
- If the field list is empty, stop and ask the requester: "what data flows through this change?"

### Phase 2 · Tier classification
For each field, walk the `reference/data-tier-rubric.md` decision tree.

Common traps to avoid:
- **`patient_id` is L4** even if hashed at rest — the unhashed source still exists somewhere
- **Aggregate counts > 5 patients are L3**, not L2; small-N cohorts are re-identifiable
- **Doctor / hospital names are L2-L3**, not L1, because they bound the population
- **Free-text `notes` / `description`** is L4 by default until proven otherwise (notes leak PHI 100% of the time)

The change's tier = max(field tiers).

### Phase 3 · Field minimization challenge
For every field marked L3/L4, ask **three times**:
1. Can the feature work without this field?
2. Can a coarser version work? (e.g. age_bucket instead of birth_date)
3. Can we project / hash / aggregate it at the source so it never enters the change?

Remove every field that cannot defend its inclusion. Document the rationale.

### Phase 4 · Model allowlist derivation
Look up `reference/model-deployment-matrix.md`. The rule:

| Change tier | Coder model | Reviewer model | Architect model | Allowlist defaults |
|---|---|---|---|---|
| L1 | any | any | any | broad (still recorded) |
| L2 | China-cloud enterprise API + private | China-cloud enterprise API + private | Claude Opus allowed (zero-PHI design only) | medium |
| L3 | private deployment **preferred**; China-cloud enterprise API allowed only after `phi-desensitize` | same | architect work must be PHI-free abstract; Claude Opus allowed | tight |
| L4 | private deployment **mandatory**, post-desensitization | private mandatory | architect MUST work on abstract schema, never raw field names mapped to real patients | strict; explicit deny on overseas public |

Write the result to `MODEL_ALLOWLIST.json`.

### Phase 5 · Risk statement
Fill the risk table in `COMPLIANCE_TAG.md`. Every "Yes" must point at a concrete mitigation (Skill / Hook / process).

### Phase 6 · Signature handoff
- During M1-M3 (transition): co-signed by QA Lead + Legal Counsel.
- From M4: Compliance Officer signs.

The signature MUST go into the file (name + date), not via external system.

### Phase 7 · Injection
Run `mcp-model-router.injectAllowlist(change_id, allowlist_json)`. If injection fails, **stop and escalate** — never proceed with a stale or absent allowlist.

## Hard gate checklist (must all be true before exit)

- [ ] Field list is non-empty (or explicit `no_data: true` justification)
- [ ] Every field has a tier assigned by rubric
- [ ] Change tier = max(field tiers), written in COMPLIANCE_TAG
- [ ] Every L3/L4 field has passed the 3-question minimization challenge
- [ ] MODEL_ALLOWLIST.json valid against schema
- [ ] All "Yes" risks have mitigation
- [ ] Signed by authorized signer(s)
- [ ] Injected into mcp-model-router (verify via router echo response)

## Common failure modes

1. **"It's just internal" inflation**: developers mark L4 as L2 because data stays in-house. Wrong: tier is about *kind of data*, not *current location*. Mitigation: when in doubt, classify up.
2. **Field-list amnesia**: business spec mentions 5 fields, dev later reads 15. Mitigation: this skill must be re-run when scope changes; the COMPLIANCE_TAG version field exists for this.
3. **Allowlist drift**: tag says "private only" but allowlist accidentally includes `claude-opus-public`. Mitigation: this skill must regenerate allowlist from tier, never hand-edit.
4. **Sign-and-forget**: signed once, never revisited for 6 months as scope changes. Mitigation: change v1.0 → v1.1 forces re-signature for any scope expansion.

## Output handoff

Hand off to Step 1 (`prd-implementation-precheck`) with:
- Path to COMPLIANCE_TAG.md
- Path to MODEL_ALLOWLIST.json
- Optional: a one-paragraph "tier summary" for PM-Agent to embed in the PRD's compliance section
