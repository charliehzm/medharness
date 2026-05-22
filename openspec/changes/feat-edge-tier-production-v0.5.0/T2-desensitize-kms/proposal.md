# Proposal · T2 desensitize cryptography + FileKeyProvider

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task: `T2 · desensitize → cryptography + FileKeyProvider`
> Status: spec-only decomposition for maintainer review

---

## 1. One Sentence

T2 turns `mcp-desensitize` into a local edge-tier desensitization backend with a `KeyProvider` abstraction, AES-256-GCM encrypted reverse mapping, FileKeyProvider custody, rotation support, and ClickHouse `_phi_lookup` schema.

## 2. Scope

In scope for T2:

- Define `KeyProvider` abstraction and foundational crypto / envelope types.
- Implement `FileKeyProvider` for v0.5.0 edge tier.
- Enforce local key file permissions (`chmod 400`).
- Implement AES-256-GCM envelope encryption for reverse mappings.
- Support key rotation while keeping old encrypted mappings decryptable.
- Integrate `server_v2.py` with the crypto envelope and FileKeyProvider.
- Define ClickHouse `_phi_lookup` reverse mapping schema.
- Add provider skeletons for Vault / Aliyun KMS / AWS KMS without implementing cloud calls.
- Add integration tests for roundtrip, rotation, and chmod behavior.
- Produce T2 audit summary and sign-off.

Out of scope for T2:

- Real Vault / Aliyun KMS / AWS KMS calls.
- Cloud credentials, customer-specific KMS config, or production customer markers.
- HA / distributed key custody.
- Real PHI fixtures.
- `mcp-audit-log` ClickHouse implementation; that remains T4.

## 3. Inputs From T1

T2 can rely on T1 outputs:

- `server_v3.detect_v3(text)` returns `spans` and `stats`.
- Spans contain `start`, `end`, `entity_type`, `score`, and `text_sha256`.
- Detector response does not return raw matched text.
- T1.7 synthetic fixtures are available for regression testing.
- `tools/phi_fingerprint_check.py --strict` validates fixture compliance.

T2 must not assume:

- `CN_NAME` exists.
- Real PHI is allowed in tests.
- Negative FP scan is already part of the main red-team runner.

## 4. Crypto Primitive Decision

This task group follows the corrected decision recorded in `main` commit `8753d41`:

- Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- Do not use legacy placeholder crypto in the final T2 implementation.
- Require 32-byte raw keys for AES-256-GCM.
- Generate 96-bit random nonces per encryption.
- Bind associated data to `schema_version`, `algorithm`, `change_id`, `map_id`, and `key_id`.
- Treat the current `server_v2.py` legacy placeholder crypto path as migration debt, not the T2 target.

## 5. Compliance Posture

| Red line | T2 posture |
|---|---|
| R1 PHI never raw into prompt | T2 code must desensitize before any prompt path; tests use synthetic only. |
| R2 model allowlist | T2 adds no model calls. |
| R3 audit full record | T2 records audit expectations but does not implement audit-log backend; T4 owns WORM implementation. |
| R4 synthetic test data | T2 tests must use synthetic payloads and pass fingerprint checker where fixtures are added. |
| R5 license | No license changes. |

## 6. Data Classification

T2 touches the most sensitive local runtime path in the edge tier:

- Input payload may be L3 / L4.
- Reverse mapping contains recoverable PHI and must be treated as L4.
- Key files are security secrets and must never enter git, prompt logs, CI logs, PR bodies, or test snapshots.
- `map_ref` and encrypted blobs are still sensitive operational metadata.

Implementation rule:

- Never print plaintext mapping values.
- Never return raw reverse mapping in health endpoints.
- Never include key bytes in exceptions.
- Never include plaintext PHI in audit artifacts.

## 7. Storage Model

v0.5.0 storage target:

- Key material: local file keystore under `/data/medharness/keystore/*.key`.
- Reverse mapping metadata: ClickHouse `_phi_lookup` schema defined in T2.
- Actual ClickHouse write integration can remain light in T2 if T4 audit infrastructure is not ready, but schema must be ready for deployment packaging.

## 8. Acceptance Rollup

T2 is complete only when:

- All T2.1-T2.10 leaves are merged.
- `FileKeyProvider` creates and loads AES-256 keys.
- New key files are mode `0400`.
- Existing keys with weaker permissions fail closed.
- AES-256-GCM encrypt / decrypt roundtrip passes.
- Rotation creates new active key while old encrypted mappings remain decryptable.
- `server_v2.py` no longer uses base64 or other legacy placeholder encryption for production map encryption.
- Reverse mapping schema is documented in SQL.
- Cloud provider skeletons exist but do not call networks.
- Integration tests cover roundtrip, rotation, chmod, and no raw map leakage.
- Dryrun remains green.
- T2 audit summary signs off R1-R5.

## 9. Key Risks

| Risk | Mitigation |
|---|---|
| AES-256-GCM implementation drift | T2.2 review explicitly uses AESGCM before code implementation. |
| Key file permission drift | FileKeyProvider must fail closed unless key file mode is exactly `0400` or stricter platform-equivalent behavior is documented. |
| Nonce reuse | AESGCM helper owns nonce generation; tests assert nonces differ across encryptions. |
| Old map undecryptable after rotation | Envelope stores `key_id`; provider keeps old keys until retention policy deletes them. |
| Raw PHI leakage through `map_blob` | Server integration tests assert no plaintext original values in response envelope. |
| Cloud skeleton accidentally calls network | Skeletons raise `NotImplementedError` and contain no SDK imports. |
| ClickHouse schema overreaches T4 | T2 only defines `_phi_lookup`; T4 owns `_audit_log` WORM. |

## 10. Notes For Parallel Work

- PR #27 independently promotes the negative FP gate into `run_all.sh`; it does not block T2.
- No separate duplicate spec file is needed for this group. The group-level `proposal.md` and `tasks.md` are the canonical spec.

## 11. T2 -> T3/T4/T13 Handoff

T3 can assume T2 adds no LLM call path.

T4 can consume T2 event expectations for desensitize / reverse audit events.

T13 can package:

- `mcp/desensitize/key_provider/`
- `mcp/desensitize/crypto_envelope.py`
- ClickHouse `_phi_lookup` schema.
- Empty keystore directory scaffold, never real keys.
