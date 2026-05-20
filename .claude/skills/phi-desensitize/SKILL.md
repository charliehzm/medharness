---
name: phi-desensitize
description: >
  Use this skill before any prompt, log message, error trace, test fixture, or
  external API call that may include patient health information (PHI) or
  personal identifying information (PII) in a medical-data SaaS context.
  Replaces sensitive tokens with reversible synthetic substitutes, emits a
  desensitize map (encrypted), and produces a residual-risk report. Mandatory
  pre-stage before any L3/L4 data ever enters a model context window. Chinese
  trigger examples: "脱敏", "PHI 脱敏", "数据脱敏", "去标识化", "patient_id
  替换", "把这段日志脱敏", "把样例匿名化". Do NOT use as a one-way redactor
  when the workflow needs round-trip mapping; do NOT use for fully synthetic
  data that contains no real source values (use test-data-generation instead).
  Success = every L3/L4 token in input is replaced, output passes
  mcp-phi-detector with zero hits, reversal map is encrypted with KMS-managed
  key, and residual-risk report is empty or explicitly approved.
compatibility: Requires file read/write; integrates with mcp-phi-detector (M2+), mcp-desensitize (M2+), and KMS. May fall back to local regex/rule engine if MCP servers are offline (CPU-only).
metadata:
  version: "1.0"
  owner: "data-steward"
  category: "compliance-runtime"
  maturity: "production"
  sop_step: "cross-cutting"
  hard_gate: true
  outputs: "desensitized text/payload + .desensitize_map.json.enc + residual_risk_report.md"
---

# PHI Desensitize

The single most important runtime gate in the entire AI Coding system: **no L3/L4 token should ever enter a model context window without first passing through this skill.**

## Core mental model

Desensitization is **not redaction**. Redaction destroys information; desensitization replaces it with reversible placeholders so the downstream LLM can still reason about structure and relationships, while the operator can reverse the mapping on a vetted output in a controlled environment.

```
"Patient 张三 (ID 110101199001011234) seen 2026-03-12"
   ↓ desensitize
"Patient {{PT_A1}} (ID {{ID_B7}}) seen {{DATE_C3}}"
   ↓ LLM reasons, produces analysis referencing {{PT_A1}}
   ↓ controlled reversal in approved environment
"Patient 张三 (ID 110101199001011234) seen 2026-03-12 — diagnosis: ..."
```

## What this skill produces

For each invocation:
1. `desensitized_payload` — sanitized text / JSON / fixture
2. `<source>.desensitize_map.json.enc` — encrypted reversal map (AES-256-GCM, key from KMS)
3. `residual_risk_report.md` — listing any tokens the classifier was uncertain about

## When NOT to use this skill

Skip for:
- Already fully synthetic data (use `test-data-generation` instead)
- Purely L1 / public content (no PHI possible)
- One-way logging where reversal is never needed (use simple redaction)
- Encryption / hashing at storage layer (that's data-at-rest concern, different domain)

## Active context bundle

**Always load first**
1. This `SKILL.md`
2. `reference/hipaa-18-identifiers.md` — the canonical PHI taxonomy
3. `reference/cn-personal-info-catalog.md` — 公安部 / 健康医疗数据安全指南 PII categories
4. `reference/detection-rules.md` — regex + ML classifier combination strategy

**Load on demand**
- `reference/free-text-strategy.md` — for unstructured notes / discharge summaries
- `reference/structured-data-strategy.md` — for JSON / CSV / Parquet payloads
- `reference/reversal-protocol.md` — when reversal is needed in approved environment

## Detection strategy (dual-pass)

### Pass 1 — Rule layer (deterministic, high recall)
- **CN-ID regex**: `\d{17}[\dXx]` after Luhn-like check digit
- **CN-phone regex**: `1[3-9]\d{9}`
- **CN-name heuristic**: 2-4 CJK chars in subject position of sentence
- **Birth date**: `\d{4}[-/年]\d{1,2}[-/月]\d{1,2}` — combined with name proximity bumps tier
- **Medical record number**: pattern depends on hospital; load org-specific patterns from `reference/org-mrn-patterns.md`
- **18 HIPAA identifiers**: see reference

### Pass 2 — Classifier layer (high precision)
- Local fine-tuned BERT or Qwen-1.8B running CPU
- Confirms / rejects Pass 1 candidates
- Catches **free-text PHI** missed by regex (e.g. "the man whose wife works at Tongji")

### Pass 3 — Disagreement resolution
- If rule says PHI but classifier disagrees: still desensitize (false positive is cheap)
- If classifier says PHI but rule didn't: desensitize + log to `residual_risk_report` (for rule library update)

## Substitution scheme

Each detected token → `{{TYPE_SHORTID}}` where:
- `TYPE` ∈ {PT (patient), ID (identifier), DR (doctor), HS (hospital), DT (date), AD (address), PH (phone), MR (medical record), DX (diagnosis sometimes), TX (treatment sometimes)}
- `SHORTID` is a 2-char base32 from a per-session HMAC of the original value, so the same input within a session gets a stable placeholder (preserves relationships)

The map stores `{placeholder: original}` and gets encrypted before being written to disk.

## Reversal protocol (controlled)

Reversal is **opt-in and audited**:

1. Reversal can only happen inside the project's `.controlled/` directory (mounted read-only outside dev environment)
2. Reversal requires:
   - Active developer session with Data Steward signoff
   - The `.desensitize_map.json.enc` from the same change
   - KMS access (logged centrally)
3. Reversed output is treated as L4 immediately upon reversal — no copying to other locations

## Hard gate checklist

- [ ] Every L3/L4 token in the source has been replaced
- [ ] Output passes `mcp-phi-detector` with zero hits (hooked at UserPromptSubmit, double-check)
- [ ] Desensitize map encrypted with KMS-managed key (no plaintext map on disk)
- [ ] Residual risk report empty OR every entry has owner ack
- [ ] If used inside a Skill chain, the desensitized payload is what flows downstream — never the original

## Common failure modes

1. **Half-desensitized fixtures**: dev manually replaced names but forgot phone numbers. Mitigation: always run both passes, never trust manual cleanup.
2. **Map leakage**: developer puts the unencrypted map in repo. Mitigation: hook `PreToolUse` to deny `Write(*.desensitize_map.json)` (no `.enc` suffix).
3. **Cross-change collisions**: same patient appears in two changes, placeholders differ — that's fine and intentional (no cross-change linkability). Don't try to "harmonize" across changes.
4. **Free-text re-identification**: "the 38-year-old male diabetic seen in Shanghai United on 2026-03-12" — even with name removed, this is identifying. Detection must consider co-occurrence. The classifier layer is your defense; rule layer alone is insufficient.
5. **Date shifting confusion**: for time-series analysis, simply masking dates breaks reasoning. Use **date shifting**: add a per-patient random offset that preserves intervals. Document the shift in the map.

## Integration points

- **At Hook layer**: `UserPromptSubmit` runs `mcp-phi-detector` as a tripwire; if it fires AFTER this skill, something is wrong (regression or new vector)
- **At MCP layer**: `mcp-desensitize` exposes this skill's logic as a callable tool so non-conversation flows (CI, batch jobs, MCP-using sub-agents) can use it programmatically
- **At SOP layer**: invoked before any prompt in Steps 5 (mock data), 6 (apply), 8 (review), 9 (mocking test) that touches L3/L4

## Output handoff

Returns:
- Desensitized payload (use as-is downstream)
- Path to encrypted map (for controlled reversal later)
- Residual risk report (must be empty or signed off)
