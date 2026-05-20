---
name: compliance-review
description: >
  Use this skill at Step 10 of the v2 SOP, executed by the Compliance-Agent
  (whose backing model must be heterogeneous from the main orchestrator), to
  produce a COMPLIANCE_REPORT.md for a change that has passed functional Verify
  and code review. Audits PHI handling, prompt-injection surface, model-call
  conformance to MODEL_ALLOWLIST, and test-data lineage. Outputs risk-tiered
  findings (High / Medium / Low) with concrete remediation pointers. Chinese
  trigger examples: "合规审查 Gate", "Step 10", "合规扫描", "PHI 泄漏检查",
  "数据流图审查", "出 COMPLIANCE_REPORT". Do NOT use as a substitute for Step 8
  code review, do NOT use before Step 7 Verify passes (functional bugs distort
  compliance signal). Success = signed COMPLIANCE_REPORT.md with high-risk = 0,
  every medium-risk has owner + remediation, no PHI leak found in logs /
  exceptions / cache layers.
compatibility: Requires read access to change diff, prompt history (audit log), test fixtures, model routing log. Must run on a model heterogeneous from the change's coder model (deny same-model self-audit).
metadata:
  version: "1.0"
  owner: "compliance-committee"
  category: "compliance-gate"
  maturity: "production"
  sop_step: 10
  hard_gate: true
  outputs: "openspec/changes/<slug>/COMPLIANCE_REPORT.md"
---

# Compliance Review (Step 10)

The Compliance Gate. Functional correctness was proven by Verify; this skill proves **compliance correctness**.

## Core mental model

You are looking for **four classes of risk** in a change that already works:

1. **PHI leakage**: data that should not have escaped the controlled zone (logs, exceptions, caches, external API payloads)
2. **Prompt-injection surface**: new ingress paths where untrusted text reaches a model
3. **Model-call non-conformance**: any LLM invocation outside `MODEL_ALLOWLIST.json`
4. **Test-data lineage breach**: synthetic data that turns out to be reversible to real patients

Functional tests don't catch any of these — they test what's intended. You test what's *unintended*.

## Why heterogeneous model?

If the change's coder used DeepSeek-V4-Pro and Compliance-Agent also uses DeepSeek-V4-Pro, you get correlated blind spots — both will overlook the same prompt-injection style. **The Compliance-Agent's backing model MUST be a different family** (e.g. Qwen if coder used DeepSeek, or vice versa). This is enforced by mcp-model-router; do not try to override.

## What this skill produces

`openspec/changes/<slug>/COMPLIANCE_REPORT.md` with this exact section structure:

```
# COMPLIANCE_REPORT — <change_id>
## 1. Audit metadata (auditor model id, date, inputs)
## 2. Findings — High Risk        (must be 0 to pass)
## 3. Findings — Medium Risk      (each needs owner + remediation)
## 4. Findings — Low Risk         (informational)
## 5. PHI handling assessment
## 6. Prompt-injection surface assessment
## 7. Model-call conformance assessment
## 8. Test-data lineage assessment
## 9. Sign-off block
```

## When NOT to use this skill

Skip for:
- Changes that have not yet passed Step 7 Verify (functional bugs first)
- Pure docs / build / CI changes touching no L3/L4 path (use lightweight checklist instead)
- Bug-fix-only changes inside an already-archived bundle (those go through Step 11 mini-loop)

## Active context bundle

**Always load first**
1. This `SKILL.md`
2. `reference/checklist-phi-leakage.md` — concrete patterns to grep / inspect
3. `reference/checklist-prompt-injection.md` — RAG / tool-result / external-doc patterns
4. `reference/checklist-model-conformance.md` — how to match routing log against allowlist
5. `reference/checklist-test-data-lineage.md` — fingerprint comparison protocol

**Load on demand**
- The change's `COMPLIANCE_TAG.md` and `MODEL_ALLOWLIST.json`
- The change's `diff.patch`
- The change's audit log slice (prompt history, tool calls)
- The change's test data + fingerprints
- `reference/severity-rubric.md` — how to grade findings

## Workflow

### Phase 1 · Inputs assembly (≤ 10 min)
- Pull from change directory: diff, prompts log, tool calls log, routing log, test data fingerprints, COMPLIANCE_TAG
- Generate a data-flow diagram (or reuse the one from Step 3 design.md compliance section)
- Verify auditor model heterogeneity (assert routing_log.coder_model ≠ self.model_id)

### Phase 2 · PHI leakage sweep
Walk `checklist-phi-leakage.md`. Key probes:
- Are L3/L4 field values present in any newly-added log statement, exception message, error response body, cache key, or audit trail formatting?
- Are L3/L4 field names exposed in serialized error contexts to clients?
- Did the change introduce any new external API call whose payload could include L3/L4?
- Did any new background job persist L3/L4 to a location outside the controlled storage?

Each hit → finding. Severity by data tier (L4 hit → High; L3 hit → Medium unless aggregated; L2 hit usually Low).

### Phase 3 · Prompt-injection surface sweep
Walk `checklist-prompt-injection.md`. Key probes:
- Did the change introduce a new RAG path? Does it pass retrieved content through `prompt-injection-scan`?
- Are user-provided text fields reaching a model without sanitization?
- Are tool results (e.g. SQL query results, web fetches) interpreted as instructions rather than data?
- Are any new model-callable tools exposed without authorization checks?

### Phase 4 · Model-call conformance
For every model invocation recorded in the audit log slice:
- model_id ∈ MODEL_ALLOWLIST.coder ∪ reviewer ∪ architect ∪ compliance ∪ docs?
- deployment matches what allowlist expects (private / China-cloud / public)?
- For L4-tier changes: every call's prompt confirmed desensitized (placeholder pattern present)?

Any non-match → High (this is a hard policy breach, not a code smell).

### Phase 5 · Test-data lineage
- Compute fingerprints over the change's synthetic test data
- Compare against the real-sample fingerprint library (held by Data Steward)
- Any near-collision → High and stop (potential reversal)
- Verify `source_declaration.md` in test_data/ asserts synthetic-only

### Phase 6 · Findings assembly
For each finding fill:
- **Title** (one line)
- **Severity** (High / Medium / Low)
- **Evidence** (file:line / log slice id / fingerprint hash)
- **Why** (which rule / clause violated)
- **Remediation pointer** (skill / fix suggestion / who owns it)

### Phase 7 · Sign-off
Compliance Officer signs only if High = 0. Medium with owner + plan is acceptable but must be tracked.

## Hard gate checklist

- [ ] Auditor model heterogeneity verified (not same as coder)
- [ ] PHI leakage sweep complete with explicit "checked" mark per category
- [ ] Prompt-injection sweep complete
- [ ] Every model call in routing log mapped to allowlist entry
- [ ] Test data fingerprints validated against real-sample library
- [ ] Findings sectioned by severity
- [ ] Every Medium has owner + remediation
- [ ] Every High is either fixed (route to Step 11) or signed off as accepted risk by Compliance Officer with documented compensating control (rare)
- [ ] Report saved to `openspec/changes/<slug>/COMPLIANCE_REPORT.md`

## Common failure modes

1. **Auditor model collusion**: forgot to enforce heterogeneity, same model self-audits → blind to its own pattern errors. Mitigation: hard assertion in Phase 1.
2. **"It's fine, no PHI shown" handwave**: skill produces empty High section without evidence trail. Mitigation: every sweep MUST emit a "checked" log entry per category, even if empty.
3. **Treating Medium as "TODO later"**: medium findings accumulate as tech debt, eventually become P0. Mitigation: each Medium has named owner + due date; surfaced in monthly compliance committee review.
4. **Verifying allowlist by name only**: routing log may contain `model_id: "deepseek-v4"` while allowlist says `"deepseek-v4-pro"` — close but not the same SKU. Match exactly, not by substring.
5. **Fingerprint comparison shortcut**: skipping fingerprint check because "we used the official generator". Generators can still leak source values. Always compute and compare.

## Integration

- **Triggered by**: Step 9 completion → SOP gate activates Step 10
- **Triggers**: if High > 0 → Step 11 remediation loop; if High = 0 and Medium > 0 → can proceed to Step 12 with monitoring; if all clean → Step 12 directly
- **Audit trail**: this report is itself part of AUDIT_BUNDLE.compliance/

## Output handoff

If High = 0: return path to COMPLIANCE_REPORT.md and signal "Step 12 ready".
If High > 0: return findings list + recommend `systematic-debugging` + `openspec-apply-change` to remediate, then re-run this skill.
