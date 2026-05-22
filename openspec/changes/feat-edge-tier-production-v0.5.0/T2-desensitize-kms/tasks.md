# T2 · desensitize cryptography + FileKeyProvider · leaf task plan

> Parent task group: `T2 · desensitize → cryptography + FileKeyProvider`
> Parent task list: `../tasks.md`
> Branch model: each leaf starts from `main` as `feat/T2.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 substantive files.
- 3 files are allowed only when the 3rd file is wiring-only, <= 15 changed lines, and necessary.
- 4+ files must be split.
- All tests use synthetic payloads only; no real PHI may enter fixtures, prompts, logs, or PR text.
- Key bytes must never be printed, committed, or included in exceptions.
- Cloud KMS providers are skeleton-only in T2; no network calls, SDK imports, credentials, or cloud config.
- T2 implementation must not bypass `mcp-audit-log`; if audit backend is not ready, write explicit audit handoff notes for T4.
- T2 is not complete until AES-256-GCM roundtrip, key rotation, chmod validation, and T1 detector compatibility are verified.

## Crypto Contract For Implementation Leaves

T2 follows the corrected crypto decision already recorded in `main` commit `8753d41`:

- Production envelope primitive: `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- Key size: 32 raw bytes per key id.
- Nonce: 12 random bytes per encryption.
- AAD: schema version, algorithm, `change_id`, `map_id`, and `key_id`.
- Envelope metadata must include enough information to select old keys during decrypt.
- Existing `server_v2.py` placeholder encryption path is migration debt, not the final primitive.

## Leaf Sub-tasks

### T2.1 · KeyProvider interface and foundational types ✅

- Branch: `feat/T2.1-key-provider-interface`
- PR: [#29](https://github.com/charliehzm/medharness/pull/29)
- Merge commit: `3810b62`
- Leaf commit: `d3cca85`
- Files:
  - `mcp/desensitize/key_provider/__init__.py`
  - `mcp/desensitize/key_provider/interface.py`
- Scope:
  - Define `KeyProvider` abstract interface: `get_key(key_id) -> bytes`, `rotate(key_id) -> bytes`, `list_keys() -> list[str]`.
  - Add foundational dataclasses / typed aliases needed by later leaves, including envelope metadata if they fit cleanly in `interface.py`.
  - Define typed exceptions that fail closed without exposing key bytes or plaintext mapping values.
- Acceptance:
  - Importing `mcp/desensitize/key_provider` succeeds without cloud SDKs or network.
  - Interface docstrings state key byte secrecy and no-logging rules.
  - `python -m compileall mcp/desensitize/key_provider` passes.
  - No PHI fixtures, no LLM, no network.
- Result: completed and merged. KeyProvider contracts, typed aliases, envelope metadata, and fail-closed exceptions are available.

### T2.2 · AES-256-GCM crypto envelope helper ✅

- Branch: `feat/T2.2-aesgcm-envelope`
- PR: [#30](https://github.com/charliehzm/medharness/pull/30)
- Merge commit: `5261dcd`
- Leaf commit: `5b8565e`
- Files:
  - `mcp/desensitize/crypto_envelope.py`
  - `tests/test_desensitize_crypto_envelope.py`
- Scope:
  - Implement AESGCM encrypt / decrypt helpers for reverse mapping JSON.
  - Generate a fresh 12-byte nonce per encryption.
  - Bind AAD to `schema_version`, `algorithm`, `change_id`, `map_id`, and `key_id`.
  - Return a serializable envelope with `ciphertext`, `nonce`, `key_id`, `algorithm`, and `schema_version`.
  - Reject wrong key / wrong AAD / malformed envelope without returning plaintext.
- Acceptance:
  - Roundtrip passes with 32-byte synthetic key.
  - Same plaintext encrypted twice produces different nonce / ciphertext.
  - Wrong AAD fails.
  - Wrong key fails.
  - Serialized envelope does not include raw mapping values.
  - No network, no cloud KMS in this helper.
- Result: completed and merged. AES-256-GCM helper with canonical AAD, metadata hash, and fail-closed decrypt contract is in place.

### T2.3 · FileKeyProvider initial implementation ✅

- Branch: `feat/T2.3-file-key-provider`
- PR: [#31](https://github.com/charliehzm/medharness/pull/31)
- Merge commit: `1a42527`
- Leaf commit: `5b5f891`
- Files:
  - `mcp/desensitize/key_provider/file_provider.py`
  - `tests/test_desensitize_file_key_provider.py`
- Scope:
  - Implement local file-backed provider for `/data/medharness/keystore/*.key` with configurable root for tests.
  - Create missing key files atomically with 32 random bytes.
  - Enforce key filename sanitization.
  - Write new key files with mode `0400`.
  - Refuse to read key files with group / world permissions.
- Acceptance:
  - New key is 32 bytes.
  - Created file mode is `0400` on POSIX.
  - Existing `0644` key fails closed.
  - Invalid key id fails.
  - Exceptions do not include key bytes.
  - No network, no cloud KMS.
- Result: completed and merged. FileKeyProvider creates 32-byte local keys under a secured keystore root and fails closed on unsafe permissions.

### T2.4 · FileKeyProvider rotation and old-key decrypt support ✅

- Branch: `feat/T2.4-key-rotation`
- PR: [#32](https://github.com/charliehzm/medharness/pull/32)
- Merge commit: `1afd2cb`
- Leaf commit: `1a03cde`
- Files:
  - `mcp/desensitize/key_provider/file_provider.py`
  - `tests/test_desensitize_file_key_provider.py`
- Scope:
  - Add active key pointer / naming convention for rotated keys.
  - Implement `rotate(key_id)` so new encryptions use the newest key.
  - Preserve old key material for decrypt by explicit old `key_id`.
  - Ensure `list_keys()` returns deterministic, sanitized key ids.
  - Keep file permissions enforced for all generations.
- Acceptance:
  - Rotation creates a different 32-byte key.
  - Decrypt with envelope old `key_id` still works after rotation when paired with T2.2 helper in test.
  - `list_keys()` includes old and active key ids.
  - Any permission violation fails closed.
  - No network, no cloud KMS.
- Result: completed and merged. Generation-based rotation, legacy migration, old-key decrypt, and prune semantics are implemented.

### T2.5 · server_v2 crypto integration ✅

- Branch: `feat/T2.5-server-v2-crypto`
- PR: [#33](https://github.com/charliehzm/medharness/pull/33)
- Merge commit: `b3e498a`
- Leaf commit: `1213a43`
- Files:
  - `mcp/desensitize/server_v2.py`
  - `tests/test_desensitize_server_v2_crypto.py`
- Scope:
  - Replace placeholder base64 / derived map encryption with FileKeyProvider + AESGCM envelope.
  - Keep CLI and stdio compatibility for `health`, `desensitize`, and `reverse`.
  - Ensure `map_ref` identifies encrypted mapping without exposing plaintext.
  - Ensure response envelope does not leak raw reverse mapping values.
  - Keep reverse token requirement and fail closed on missing / invalid token.
  - If direct ClickHouse write is not ready, isolate schema-backed persistence behind a local adapter boundary for T2.6/T4 handoff.
- Acceptance:
  - `desensitize` roundtrip with synthetic CN ID / phone / email through `reverse` works only with valid token.
  - Invalid token returns denial and no plaintext.
  - Health does not return key bytes, paths with secrets, or map contents.
  - `map_blob` is removed or replaced by encrypted envelope field that contains no raw values.
  - Existing CLI / stdio smoke remains compatible.
  - No real PHI, no cloud KMS, no model calls.
- Result: completed and merged. `server_v2` now encrypts reverse mappings with FileKeyProvider + AES-GCM and gates reverse by token.

### T2.6 · ClickHouse `_phi_lookup` schema ✅

- Branch: `feat/T2.6-phi-lookup-schema`
- PR: [#34](https://github.com/charliehzm/medharness/pull/34)
- Merge commit: `2df19ef`
- Leaf commit: `3eccb81`
- Files:
  - `mcp/desensitize/sql/phi_lookup.sql`
  - `tests/test_desensitize_phi_lookup_schema.py`
- Scope:
  - Define ClickHouse table schema for encrypted reverse mapping lookup metadata.
  - Include `map_id`, `change_id`, `key_id`, `algorithm`, encrypted envelope payload, created timestamp, retention metadata, and hash fields for integrity.
  - Avoid storing plaintext original values.
  - Add parser / text tests that assert unsafe columns are absent.
- Acceptance:
  - SQL contains no plaintext PHI columns such as `original`, `raw_text`, `patient_name`, or `phone`.
  - SQL contains indexed lookup fields needed for reverse.
  - Schema clearly separates `_phi_lookup` from T4 `_audit_log`.
  - Tests pass without running ClickHouse.
- Result: completed and merged. ClickHouse `_phi_lookup` DDL is defined and schema-tested without requiring a live ClickHouse instance.

### T2.7 · Integration tests for roundtrip, rotation, and chmod ✅

- Branch: `feat/T2.7-integration-tests`
- PR: [#35](https://github.com/charliehzm/medharness/pull/35)
- Merge commit: `f506cbf`
- Leaf commit: `d3d5c99`
- Files:
  - `tests/test_desensitize_t2_integration.py`
  - `mcp/desensitize/key_provider/file_provider.py`
- Scope:
  - Add synthetic-only integration coverage for end-to-end desensitize / reverse.
  - Cover key rotation with old encrypted map decrypt.
  - Cover chmod failure path.
  - Cover no raw map leakage in response JSON.
  - Use sqlite3 in-memory mock for `_phi_lookup` persistence checks without starting ClickHouse.
- Acceptance:
  - Roundtrip passes.
  - Rotation test proves old map decrypt works.
  - `0644` key file fails.
  - T2.7 5-scenario integration suite passes.
  - No real PHI.
- Result: completed and merged. Five cross-module scenarios cover happy path, rotation, prune, chmod tamper, and R1 no-leak behavior.

### T2.8 · Vault and Aliyun KMS skeleton providers ✅

- Branch: `feat/T2.8-vault-aliyun-kms-skeletons`
- PR: [#36](https://github.com/charliehzm/medharness/pull/36)
- Merge commit: `12687f2`
- Leaf commit: `73bed03`
- Files:
  - `mcp/desensitize/key_provider/vault_provider.py.skel`
  - `mcp/desensitize/key_provider/aliyun_kms.py.skel`
- Scope:
  - Add non-executable skeleton files for future v1.0 providers.
  - Document expected constructor config and methods matching `KeyProvider`.
  - Explicitly raise `NotImplementedError`.
  - Avoid cloud SDK imports, credential names, endpoints, or network calls.
- Acceptance:
  - Skeletons are clearly marked v1.0 / not implemented.
  - No imports from Vault / Aliyun SDKs.
  - No real credential examples.
  - File count stays within 2.
- Result: completed and merged. Vault and Aliyun KMS remain non-runtime `.skel` providers with v1.0 proxy-mode design tension documented.

### T2.9 · AWS KMS skeleton provider and provider handoff note ✅

- Branch: `feat/T2.9-aws-kms-skeleton`
- PR: [#37](https://github.com/charliehzm/medharness/pull/37)
- Merge commit: `77f29ed`
- Leaf commit: `ba20fe3`
- Files:
  - `mcp/desensitize/key_provider/aws_kms.py.skel`
  - `mcp/desensitize/key_provider/PROVIDER_HANDOFF.md`
- Scope:
  - Add AWS KMS skeleton matching `KeyProvider`.
  - Add provider handoff note documenting FileKeyProvider as only v0.5.0 supported provider.
  - Document that cloud providers are reserved for v1.0 and must route through enterprise compliance review before activation.
- Acceptance:
  - No AWS SDK imports.
  - No credential examples.
  - Handoff states FileKeyProvider is the only active v0.5.0 provider.
  - Handoff states cloud KMS skeletons must not be wired into runtime in T2.
- Result: completed and merged. AWS KMS remains `.skel` only and provider handoff documents v0.5 -> v1.0 proxy-mode redesign.

### T2.10 · T2 final verification and audit summary ✅

- Branch: `feat/T2.10-desensitize-verify`
- PR: pending
- Merge commit: pending
- Leaf commit: pending
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T2-desensitize-kms/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T2-desensitize-kms/tasks.md`
- Scope:
  - Record final T2 verification numbers after T2.1-T2.9 are merged.
  - Mark T2 leaf tasks complete with PRs, commits, commands, and residual risks.
  - Include R1-R5 self-check and T2 -> T3/T4/T13 handoff notes.
- Acceptance:
  - Summary includes roundtrip, rotation, chmod, fingerprint, dryrun, and red-team status.
  - `tasks.md` has completion sign-off block.
  - No code changes.
- Result: completed. Final verification summary, PR ledger, KPI snapshot, redline self-check, contract checks, residual risks, handoff notes, and retrospective are frozen in `AUDIT_BUNDLE.summary.md`.

## Dependency Order

```text
T2.1 -> T2.2 -> T2.3 -> T2.4 -> T2.5 -> T2.7 -> T2.10
                     \             \-> T2.6 -> T2.10
                      \-> T2.8 -> T2.9 -> T2.10
```

## Verification Commands Per Leaf

Run the relevant subset for every leaf, expanding as implementation accumulates:

```bash
ruff check .
ruff format .
pytest tests/
bash dryrun_e2e_v2.sh --ci
python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl --strict
```

For T2 leaves that add synthetic JSONL fixtures, also run:

```bash
python tools/phi_fingerprint_check.py <new-fixture>.jsonl --strict
```

For T2 leaves that touch desensitize crypto or reverse behavior, also run:

```bash
bash tests/red-team-drills/run_all.sh
```

## Open Review Questions

1. The group-level `proposal.md` and `tasks.md` are the canonical T2 spec; do not add a duplicate spec file.
2. Negative FP gate is handled independently and does not block T2 sequencing.
3. T2.7 should decide whether to add a new synthetic JSONL fixture or only reuse existing positive / negative test payloads if they cover the rotation / chmod path sufficiently.

## T2 完成签字

提案人 · charliehzm · 2026-05-22 ✅

Compliance Officer · charliehzm（兼任）· 2026-05-22 ✅

Tech Lead · charliehzm · 2026-05-22 ✅

Reviewer-Agent · Claude Code · 2026-05-22 ✅

T2 desensitize cryptography + FileKeyProvider · acceptance 100% met · 已可作为 T3 model-router 的 desensitize 后端 + T4 audit-log 的 envelope 数据源
