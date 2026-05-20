---
name: audit-snapshot
description: >
  Use this skill at Step 12 of the v2 SOP, after a change has passed
  compliance review (Step 10) and any remediation (Step 11), to produce the
  AUDIT_BUNDLE.tar.gz that satisfies HIPAA / PIPL / 数据安全法 / 健康医疗数据
  安全指南 6-year replayability requirements. Packages prompt history, code
  diff, compliance artifacts, test data, lineage graph, verification reports,
  model routing logs, and signatures into the canonical structure defined by
  AUDIT_BUNDLE.spec.md, computes the hash chain, and writes ROOT_SHA256 to the
  WORM-backed mcp-audit-log. Chinese trigger examples: "审计冻结", "归档审计
  包", "Step 12", "AUDIT_BUNDLE 生成", "审计快照", "上链审计". Do NOT use for
  intermediate snapshots, partial archives, or any change still in Step 10
  remediation. Success = AUDIT_BUNDLE.tar.gz exists, manifest passes schema
  validation, ROOT_SHA256 written to mcp-audit-log, LINEAGE_GRAPH invariants
  all true, bundle passes self-replay sanity check.
compatibility: Requires file read across change directory, write to bundle location, mcp-audit-log access (WORM), KMS for encryption of desensitize_map. Bundle generation must complete in one atomic operation (no partial bundles on disk).
metadata:
  version: "1.0"
  owner: "harness-engineer"
  category: "compliance-gate"
  maturity: "production"
  sop_step: 12
  hard_gate: true
  outputs: "AUDIT_BUNDLE_<change-id>_<archived_at>.tar.gz + mcp-audit-log entry"
---

# Audit Snapshot (Step 12)

The final gate. After this skill runs, the change is **frozen, replayable, and regulator-defensible** for 6 years.

## Core mental model

A bundle is not "all the files we had lying around" — it is a **time capsule** that, opened by a stranger 4 years from now during a regulatory audit, must allow them to:

1. **Reconstruct what the AI did** — every prompt, every model, every tool call
2. **Reconstruct what the code became** — base commit + diff, with hashes
3. **Reconstruct what the data was** — synthetic fixtures + fingerprints, no real patients
4. **Reconstruct who approved what** — signatures + compliance report
5. **Verify nothing has been tampered with** — hash chain + WORM ROOT_SHA256

If a stranger cannot do this in 4 hours, the bundle is invalid.

## What this skill produces

1. `<artifact-storage>/AUDIT_BUNDLE_<change-id>_<archived_at>.tar.gz` — the canonical bundle (structure defined in [openspec/templates/AUDIT_BUNDLE.spec.md](../../../openspec/templates/AUDIT_BUNDLE.spec.md))
2. WORM record in `mcp-audit-log` with ROOT_SHA256, change_id, archived_at, signers
3. Optional: a one-page `archive_summary.md` for stakeholder readout

## When NOT to use this skill

Skip for:
- Mid-change snapshots (no concept of mid-archive — bundles are final)
- Changes that haven't passed Step 10 with High = 0
- Pure documentation-only changes (still log an L1 lightweight entry, but skip full bundle if the org policy permits — usually it doesn't, default to full)

## Active context bundle

**Always load first**
1. This `SKILL.md`
2. `openspec/templates/AUDIT_BUNDLE.spec.md` — canonical structure
3. `openspec/templates/LINEAGE_GRAPH.schema.json` — invariants to enforce
4. `reference/hash-chain-protocol.md` — exact hash computation order

**Load on demand**
- `reference/replay-sanity-check.md` — self-test routine before sealing
- `reference/encryption-protocol.md` — for desensitize_map.json.enc
- `reference/signature-protocol.md` — committee signatures (M3+)

## Workflow

### Phase 1 · Pre-flight verification (≤ 5 min)
Refuse to proceed if any of these are false:
- Step 7 Verify passed
- Step 8 code review closed
- Step 9 mocking tests passed
- Step 10 `COMPLIANCE_REPORT.md` exists with High = 0
- Step 11 (if applicable) closed all High items
- `COMPLIANCE_TAG.md` exists and is signed
- `MODEL_ALLOWLIST.json` exists and was active during the change

### Phase 2 · Lineage graph generation
Walk the change directory and synthesize `lineage/LINEAGE_GRAPH.json`:
- Node types: prd / tdd / spec / task / code_module / code_file / test_case / test_data / model_call / skill_call / deploy_artifact
- Edges: derives_from / implements / tests / verifies / calls / produces / depends_on / desensitizes / audits
- **Enforce all 4 invariants** before sealing:
  - `all_code_traceable_to_spec`
  - `all_l4_fields_pass_desensitize`
  - `all_model_calls_in_allowlist`
  - `no_real_phi_in_test_data`

Any invariant false → stop; this is a structural bug in the change, not a packaging problem.

### Phase 3 · Materials collection
Collect into a staging directory:
```
staging/
├── manifest.json               (populated in Phase 4)
├── prompts/                    (from change-scoped session JSONL slices)
├── changes/                    (proposal/design/specs/tasks + diff.patch)
├── compliance/                 (COMPLIANCE_TAG, MODEL_ALLOWLIST, COMPLIANCE_REPORT, desensitize_map.enc)
├── test_data/                  (synthetic/, fingerprints.txt, source_declaration.md)
├── lineage/                    (LINEAGE_GRAPH.json, skill_call_chain.json)
├── verification/               (verify_report.md, test_results.xml, coverage.json)
├── models/                     (model_versions.json, routing_log.jsonl)
└── signatures/                 (filled in Phase 6)
```

### Phase 4 · Manifest population
Fill `manifest.json` per `AUDIT_BUNDLE.spec.md` section 2:
- schema_version, change_id, archived_at, archived_by, compliance_tier
- models_used (from routing_log)
- duration_total_seconds, skill_calls_count, tool_calls_count, prompt/completion tokens
- phi_detector_blocks (count of blocks during the change lifecycle)
- compliance_gate_outcome (must have high_risk = 0, passed = true)
- hashes (filled in Phase 5)

### Phase 5 · Hash chain computation
Per `reference/hash-chain-protocol.md`:
1. Walk staging directory in deterministic sorted order (canonical UTF-8 sort)
2. For each file compute sha256, append `sha256:<hex>  <relpath>` to `signatures/hash_chain.txt`
3. After all per-file hashes, compute ROOT_SHA256 = sha256 of concatenated hash lines
4. Write `ROOT_SHA256: sha256:<hex>` as the final line of `hash_chain.txt`
5. Populate `manifest.json.hashes` with per-file hashes

### Phase 6 · Signature collection
- Tech committee signature: `signatures/tech_committee.sig`
- Compliance committee signature: `signatures/compliance_committee.sig`
- During M1-M2 (transition): single QA Lead signature placeholder, marked `transitional: true`
- From M3: both committees sign

### Phase 7 · Sealing
1. Re-validate manifest against schema
2. Re-validate LINEAGE_GRAPH against schema (all 4 invariants true)
3. Tar+gz the staging directory: `AUDIT_BUNDLE_<change_id>_<archived_at>.tar.gz`
4. Compute sha256 of the .tar.gz file itself; this is the "outer" bundle hash
5. Atomic write to artifact storage location

### Phase 8 · WORM commit
Send to `mcp-audit-log`:
```json
{
  "event": "audit_bundle_sealed",
  "change_id": "...",
  "archived_at": "...",
  "root_sha256": "sha256:...",
  "outer_sha256": "sha256:...",
  "bundle_location": "...",
  "signers": ["tech_committee:...", "compliance_committee:..."],
  "schema_version": "1.0"
}
```
If the WORM commit fails, **do not delete the local bundle** — escalate to Harness Engineer + Compliance Officer for manual reconciliation.

### Phase 9 · Self-replay sanity check
Per `reference/replay-sanity-check.md`:
1. Extract bundle to temp location
2. Verify manifest hashes match recomputed sha256s
3. Pick one prompt from `prompts/`, validate JSONL structure
4. Pick one model_call from `routing_log.jsonl`, validate model_id ∈ manifest.models_used
5. Apply `changes/diff.patch` to base commit in scratch repo, expect clean apply
6. Re-run one test_case from verification/test_results.xml against synthetic test_data, expect match

If any check fails → bundle is malformed → escalate.

## Hard gate checklist

- [ ] All Phase 1 preconditions satisfied
- [ ] LINEAGE_GRAPH 4 invariants all true
- [ ] Manifest passes JSON schema validation
- [ ] hash_chain.txt complete with ROOT_SHA256
- [ ] Signatures present per committee policy
- [ ] Bundle tar.gz atomically written
- [ ] WORM commit succeeded (with retry on transient failure, fail-loud after retries)
- [ ] Self-replay sanity check passed

## Common failure modes

1. **Empty prompts/ directory**: change had no Claude Code prompts (manual coding). Bundle still required — fill with `prompts/no_prompts_declaration.md` explaining. Don't pretend.
2. **Hash chain non-determinism**: file walk in OS-dependent order produces different ROOT_SHA256 each run. Mitigation: explicit sorted iteration.
3. **Missing model_versions.json**: routing log says "claude-opus" but version field is empty. Audit fails because monitor cannot reproduce. Mitigation: routing log writer must record `model: id + version + deployment` always.
4. **Encrypted map with lost key**: desensitize_map.json.enc exists but KMS key has been rotated/deleted. Recovery impossible. Mitigation: KMS key rotation policy must include audit-bundle keys in retention.
5. **Schema drift**: bundle written with v1.0 spec, opened during audit when v2.0 is current. Mitigation: manifest carries schema_version; auditor tool must support N-2 schemas.
6. **WORM "best effort" failure mode**: audit-log MCP returns ok despite actually not persisting. Mitigation: WORM commit must return a receipt (storage URI + receipt hash); skill must verify receipt before declaring success.

## Integration

- **Triggered by**: completion of Step 11 (or Step 10 if no remediation needed)
- **Triggers**: ends the change lifecycle; opens permission for next change in the sequence

## Output handoff

Return:
- Path to AUDIT_BUNDLE.tar.gz
- ROOT_SHA256
- WORM receipt
- Self-replay sanity-check result

Hand to `openspec-archive-change` for final OpenSpec state transition.
