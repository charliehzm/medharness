# T2 · desensitize cryptography + FileKeyProvider · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T2 · desensitize cryptography + FileKeyProvider`
> Status: production acceptance met for T2 scope
> Date: 2026-05-22
> Scope: final verification summary only; no code in T2.10

## 1. Executive Summary

T2 moved `mcp-desensitize` from placeholder reverse-map behavior to a local edge-tier cryptographic backend.

The delivered path is intentionally conservative:

- AES-256-GCM is the only v0.5.0 envelope primitive.
- FileKeyProvider is the only executable v0.5.0 key provider.
- Reverse mapping is encrypted before it can leave `server_v2`.
- Reverse is token-gated by `COMPLIANCE_REVERSE_TOKEN`.
- ClickHouse `_phi_lookup` is defined as schema only; runtime persistence is deferred to T4.
- Vault, Aliyun KMS, and AWS KMS are documented as `.skel` providers only.

T2 is acceptable as the desensitize backend that T3 model-router can call after T1 PHI detection.

Final local verification on 2026-05-22:

- T2 focused tests: `32 passed`.
- Full repository tests: `60 passed`.
- Red-team drills: `4/4 pass`; recall `1.0`; FP `0.0`; effective recall `0.95`.
- Fixture fingerprint strict mode: pass on 220 positive / 110 negative synthetic rows.
- Dryrun CI mode: Step 0-12 pass.
- AES-256-GCM synthetic roundtrip benchmark: p99 `0.0209 ms` over 1000 encrypt+decrypt iterations.
- T2.7 integration scenarios: 5 / 5 pass.
- Contract violations observed in T2 tests: `0`.

## 2. PR Ledger

| Leaf | PR | Merge commit | Leaf commit | Summary |
|---|---:|---|---|---|
| T2.1 | [#29](https://github.com/charliehzm/medharness/pull/29) | `3810b62` | `d3cca85` | Added KeyProvider abstract interface, envelope context types, metadata, and fail-closed exceptions. |
| T2.2 | [#30](https://github.com/charliehzm/medharness/pull/30) | `5261dcd` | `5b8565e` | Added AES-256-GCM envelope helper with canonical AAD and metadata hashing. |
| T2.3 | [#31](https://github.com/charliehzm/medharness/pull/31) | `1a42527` | `5b5f891` | Added initial FileKeyProvider with chmod and safe key-id validation. |
| T2.4 | [#32](https://github.com/charliehzm/medharness/pull/32) | `1afd2cb` | `1a03cde` | Upgraded FileKeyProvider to generation-based rotation and old-key decrypt support. |
| T2.5 | [#33](https://github.com/charliehzm/medharness/pull/33) | `b3e498a` | `1213a43` | Integrated `server_v2` with FileKeyProvider + AES-GCM envelope and token-gated reverse. |
| T2.6 | [#34](https://github.com/charliehzm/medharness/pull/34) | `2df19ef` | `3eccb81` | Added ClickHouse `_phi_lookup` schema and schema tests. |
| T2.7 | [#35](https://github.com/charliehzm/medharness/pull/35) | `f506cbf` | `d3d5c99` | Added integration tests for roundtrip, rotation, prune, chmod, and R1 leak checks. |
| T2.8 | [#36](https://github.com/charliehzm/medharness/pull/36) | `12687f2` | `73bed03` | Added Vault and Aliyun KMS `.skel` providers documenting v1.0 proxy-mode tension. |
| T2.9 | [#37](https://github.com/charliehzm/medharness/pull/37) | `77f29ed` | `ba20fe3` | Added AWS KMS `.skel` provider and provider handoff note. |

## 3. Delivered Components

### 3.1 T2.1 · KeyProvider Interface

- Files: `mcp/desensitize/key_provider/__init__.py`, `mcp/desensitize/key_provider/interface.py`.
- Delivered `KeyProvider`, `EncryptionContext`, `EncryptedEnvelopeMetadata`, `PhiSpan`, and fail-closed errors.
- Interface docs forbid logging key bytes or plaintext reverse mappings.

### 3.2 T2.2 · AES-256-GCM Envelope Helper

- Files: `mcp/desensitize/crypto_envelope.py`, `tests/test_desensitize_crypto_envelope.py`.
- Delivered `encrypt_mapping`, `decrypt_mapping`, `canonical_aad`, `aad_sha256`, and `metadata_to_dict`.
- Enforces 32-byte key, fresh 12-byte nonce, canonical AAD, and fail-closed decrypt on AAD/key/tag mismatch.

### 3.3 T2.3 · FileKeyProvider Base

- Files: `mcp/desensitize/key_provider/file_provider.py`, `tests/test_desensitize_file_key_provider.py`.
- Delivered configurable file keystore, `0700` root, `0400` key files, safe key-id validation, and chmod fail-closed behavior.
- Uses `secrets.token_bytes(32)` and `tmp_path` tests.

### 3.4 T2.4 · Rotation And Old-Key Decrypt

- Files: `mcp/desensitize/key_provider/file_provider.py`, `tests/test_desensitize_file_key_provider.py`.
- Delivered `<key_id>.<generation>.key`, `get_key_by_generation`, `list_generations`, legacy migration, and max generation prune.
- Accepted trade-off: pruned generations cannot decrypt old ciphertext.

### 3.5 T2.5 · server_v2 Crypto Integration

- Files: `mcp/desensitize/server_v2.py`, `tests/test_desensitize_server_v2_crypto.py`.
- Delivered `desensitize` envelope response with `desensitized_text`, `map_ref`, and metadata.
- Delivered token-gated `reverse`; denied reverse returns safe JSON error without mapping.
- Response contract does not return `map_blob` or raw synthetic PHI.

### 3.6 T2.6 · ClickHouse `_phi_lookup` Schema

- Files: `mcp/desensitize/sql/phi_lookup.sql`, `tests/test_desensitize_phi_lookup_schema.py`.
- Delivered encrypted envelope metadata schema with `map_id`, `change_id`, `key_id`, `key_generation`, `nonce_b64`, `aad_sha256`, `ciphertext_b64`, and `ciphertext_sha256`.
- Delivered MergeTree, partition, order, TTL, and writer GRANT/REVOKE clauses.
- Boundary: schema only; real ClickHouse runtime is deferred.

### 3.7 T2.7 · Integration Tests

- Files: `tests/test_desensitize_t2_integration.py`, `mcp/desensitize/key_provider/file_provider.py`.
- Delivered five scenarios: happy path with SQLite `_phi_lookup` mock, rotation, prune, chmod tamper, and denied reverse leak check.
- Added read-only `FileKeyProvider.max_generations`.

### 3.8 T2.8 · Vault And Aliyun KMS Skeletons

- Files: `mcp/desensitize/key_provider/vault_provider.py.skel`, `mcp/desensitize/key_provider/aliyun_kms.py.skel`.
- Skeletons are parseable, non-runtime, and all methods raise `NotImplementedError`.
- No `hvac`, Aliyun SDK, credentials, or network code.
- Documents raw-byte `get_key` vs cloud proxy-mode tension.

### 3.9 T2.9 · AWS KMS Skeleton And Provider Handoff

- Files: `mcp/desensitize/key_provider/aws_kms.py.skel`, `mcp/desensitize/key_provider/PROVIDER_HANDOFF.md`.
- AWS skeleton is parseable, non-runtime, and imports no `boto3` / `botocore`.
- Handoff states FileKeyProvider is the only real v0.5 provider.
- Handoff states v1.0 must introduce `provider.encrypt` / `provider.decrypt`.

## 4. Final KPI Snapshot

| KPI | Final value | Gate | Status |
|---|---:|---:|---|
| T2 focused tests | 32 passed | pass | PASS |
| Full repository tests | 60 passed | pass | PASS |
| T2.7 integration scenarios | 5 / 5 passed | 5 / 5 | PASS |
| Red-team drills | 4 / 4 passed | pass | PASS |
| Recall / FP / effective recall | `1.0` / `0.0` / `0.95` | `>=0.92` / `<=0.15` | PASS |
| Fixture fingerprint strict mode | 2 / 2 files passed | pass | PASS |
| Contract violations | 0 observed | 0 | PASS |
| AES-256-GCM benchmark | p99 `0.0209 ms` | informational | PASS |
| chmod fail-closed coverage | T2.3, T2.4, T2.7 | covered | PASS |
| token-gated reverse denial | T2.5, T2.7 | covered | PASS |
| prune KeyNotFoundError coverage | T2.5, T2.7 | covered | PASS |
| Cloud KMS runtime imports | 0 | 0 | PASS |
| ClickHouse runtime requirement | 0 | 0 | PASS |
| dryrun e2e CI mode | pass | pass | PASS |

## 5. Reproduction Commands

### 5.1 Sync And Inspect

```bash
git checkout main
git pull --rebase
git log --oneline -20
git status
```

### 5.2 T2 Focused Tests

```bash
.venv/bin/pytest \
  tests/test_desensitize_crypto_envelope.py \
  tests/test_desensitize_file_key_provider.py \
  tests/test_desensitize_server_v2_crypto.py \
  tests/test_desensitize_phi_lookup_schema.py \
  tests/test_desensitize_t2_integration.py \
  -q
```

Expected result: `32 passed`.

### 5.3 Full Tests

```bash
.venv/bin/pytest tests/ -q
```

Expected result: `60 passed`.

### 5.4 Red-Team Drills

```bash
bash tests/red-team-drills/run_all.sh
```

Observed result:

```json
{"recall": 1.0, "effective_recall": 0.95, "false_positive_rate": 0.0, "passed": true}
```

### 5.5 Fixture Fingerprint Gate

```bash
.venv/bin/python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl --strict
```

Observed fingerprints:

- `synthetic_phi_corpus.jsonl`: `6da2fac1f3c66ab89b0695be89d70c5cf74a874249944b01348b219cc3b862c9`
- `synthetic_phi_negative_corpus.jsonl`: `faa160e6da4e2fa05884e652b4bff2320ec2b28909752a8d172f5acb293e8da5`

### 5.6 Dryrun CI Mode

```bash
bash dryrun_e2e_v2.sh --ci
```

Observed result: Step 0-12 pass.

### 5.7 AES-256-GCM Micro-Benchmark

```bash
.venv/bin/python - <<'PY'
import json, statistics, sys, time
from pathlib import Path
sys.path.insert(0, str(Path('mcp/desensitize').resolve()))
from crypto_envelope import decrypt_mapping, encrypt_mapping
from key_provider import ChangeId, EncryptionContext, KeyId, MapId
key = b'k' * 32
context = EncryptionContext(change_id=ChangeId('change-t2-final'), map_id=MapId('map-benchmark'), key_id=KeyId('active'))
mapping = {'{{ PHI_CN_ID_abcdef12 }}': 'SYNTHETIC-PHI-BENCHMARK-0001'}
latencies = []
for _ in range(1000):
    t0 = time.perf_counter_ns()
    ciphertext, metadata = encrypt_mapping(mapping, key, context)
    assert decrypt_mapping(ciphertext, metadata, key, context) == mapping
    latencies.append((time.perf_counter_ns() - t0) / 1_000_000)
latencies.sort()
print(json.dumps({'iterations': len(latencies), 'median_ms': round(statistics.median(latencies), 4), 'p95_ms': round(latencies[949], 4), 'p99_ms': round(latencies[989], 4), 'max_ms': round(max(latencies), 4)}, sort_keys=True))
PY
```

Observed result:

```json
{"iterations": 1000, "max_ms": 3.9647, "median_ms": 0.0165, "p95_ms": 0.0173, "p99_ms": 0.0209}
```

### 5.8 Skeleton Smoke And Import Guard

```bash
python3 - <<'PY'
import ast
from pathlib import Path
for path in Path('mcp/desensitize/key_provider').glob('*.skel'):
    source = path.read_text(encoding='utf-8')
    compile(source, str(path), 'exec')
    exec(source, {})
    tree = ast.parse(source, filename=str(path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or '')
    assert not ({'hvac', 'aliyunsdkcore', 'aliyunsdkkms', 'boto3', 'botocore'} & set(imports))
    print(f'{path}: ok')
PY
```

## 6. R1-R5 Self-Check

| Redline | Result | Evidence |
|---|---|---|
| R1 PHI 永不裸入 prompt | YES | T2 tests use synthetic `SYNTHETIC-PHI-*`; desensitize responses assert raw values absent. |
| R2 模型按 allowlist 路由 | YES | T2 adds no model calls and no LLM runtime path. |
| R3 审计全量记录 | YES with T4 handoff | T2 defines envelope metadata and `_phi_lookup`; T4 owns audit-log write path. |
| R4 测试数据合规 | YES | T2 uses synthetic payloads; fixture fingerprint strict mode passes. |
| R5 License 不改 | YES | T2 did not modify license files. |

R1 evidence:

- T2.2 metadata serialization excludes plaintext and key bytes.
- T2.5 desensitize and denied reverse responses exclude raw synthetic input.
- T2.6 schema forbids plaintext PHI-ish columns.
- T2.7 integration tests assert raw synthetic values are absent.

## 7. Contract Checks

### 7.1 Envelope

- AES-256-GCM only.
- 32-byte key required.
- Fresh 12-byte nonce per encryption.
- Canonical AAD binds algorithm, change_id, key_id, map_id, schema_version.
- AAD mismatch, wrong key, and tag mismatch fail closed.

### 7.2 chmod / Keystore

- Keystore root `0700`.
- Key files `0400`.
- Files broader than `0600` are rejected.
- Symlink and path traversal are rejected.
- Generation prune is explicit and tested.

### 7.3 Token-Gated Reverse

- Reverse requires `COMPLIANCE_REVERSE_TOKEN`.
- Invalid token returns permission error.
- Denied response contains no mapping.
- Pruned generation returns safe `KeyNotFoundError` JSON error.

### 7.4 Span / Placeholder Boundary

- `server_v2.desensitize` accepts T1-style `phi_spans`.
- Desensitized text is length-preserving.
- Placeholder is deterministic for the same `text_sha256`.
- T2 does not own span dedup; T1 postprocess owns that before T2.

## 8. Residual Risks And Known Limitations

1. T2.5 removed date-shifting behavior because the T2 spec did not require it.
2. T2.4 rotate-and-prune makes old ciphertext unrecoverable once the generation is deleted.
3. Vault / Aliyun / AWS KMS remain `.skel`; `PROVIDER_HANDOFF.md` documents v1.0 proxy-mode redesign.
4. `server_v2` still imports `SUBSTITUTIONS` fallback from v1 `server.py`.
5. `_phi_lookup` INSERT is not implemented in `server_v2.py`; T4 should own persistence wiring.
6. `_phi_lookup` is schema-tested with SQLite simplification, not a real ClickHouse instance.
7. `COMPLIANCE_REVERSE_TOKEN` is an alpha gate, not an enterprise authorization system.
8. `map_ref` is returned inline as base64 ciphertext in v0.5.0.
9. CN_NAME forward declaration remains from T1 and is not solved by T2.
10. `KeyProvider.get_key -> bytes` is fit for FileKeyProvider but not cloud KMS.
11. AESGCM benchmark is local developer-machine data, not a release SLO.
12. T13 packaging should re-measure in the target edge-tier image.

## 9. T2 → T3 Handoff

T3 model-router can rely on:

1. `server_v2.desensitize` accepts `phi_spans + context` and returns an encrypted envelope without raw PHI in response.
2. `server_v2.reverse` is token-gated and defaults to environment variable `COMPLIANCE_REVERSE_TOKEN`.
3. KeyProvider interface is stable for v0.5.0.
4. FileKeyProvider is the only executable v0.5.0 key provider.
5. Envelope metadata contains `key_id`, `algorithm`, `schema_version`, `nonce_b64`, `aad_sha256`, and `key_generation`.
6. ClickHouse `_phi_lookup` schema is locked for v0.5.0 handoff.
7. AES-256-GCM is the only v0.5.0 algorithm.

T3 must not assume:

1. Real cloud KMS exists.
2. Vault / Aliyun / AWS skeleton providers are executable.
3. Real ClickHouse is running.
4. `_phi_lookup` rows are automatically inserted by `server_v2`.
5. Envelope metadata includes full audit-log event metadata.
6. Reverse authorization is more than the v0.5.0 token gate.

T3 recommendation:

- Call T1 detector first.
- Pass detector spans into T2 desensitize.
- Route model prompts only after T2 desensitized output is produced.
- Log T2 metadata into T4 audit-log once T4 is ready.

## 10. Reviewer Checklist

- [ ] Confirm PR ledger matches GitHub merged PRs #29-#37.
- [ ] Confirm T2.1-T2.9 tasks are marked complete in `tasks.md`.
- [ ] Confirm this PR changes markdown only.
- [ ] Re-run focused T2 tests.
- [ ] Re-run full `pytest tests/ -q`.
- [ ] Re-run red-team drills and fixture fingerprint strict mode.
- [ ] Re-run `bash dryrun_e2e_v2.sh --ci`.
- [ ] Check residual risks are acceptable for v0.5.0 edge tier.
- [ ] Check cloud KMS remains skeleton-only.
- [ ] Check `_phi_lookup` remains schema-only.

## 11. Sign-Off

提案人 · charliehzm · 2026-05-22 ✅

Compliance Officer · charliehzm（兼任）· 2026-05-22 ✅

Tech Lead · charliehzm · 2026-05-22 ✅

Reviewer-Agent · Claude Code · 2026-05-22 ✅

T2 desensitize cryptography + FileKeyProvider · acceptance 100% met · 已可作为 T3 model-router 的 desensitize 后端 + T4 audit-log 的 envelope 数据源

## 12. 关键设计决策 retrospective

1. AES-256-GCM replaced Fernet because T2 needs explicit nonce, AAD, tag, and metadata control.
2. FileKeyProvider came first because v0.5 edge-tier must work offline.
3. Generation-based rotation enables old-envelope decrypt until prune.
4. Prune is allowed but must be paired with migration tooling before production retention windows rely on it.
5. Inline encrypted `map_ref` gave T2 safe reverse before T4 persistence existed.
6. `_phi_lookup` schema was frozen before runtime adapter work to unblock T4/T13 planning.
7. Cloud providers are `.skel` only because raw-byte `get_key` is incompatible with Vault / Aliyun / AWS KMS.
8. T2.7 was intentionally cross-module rather than another unit-test leaf.
9. Token gate is acceptable for alpha edge tier only.
10. T2.10 is markdown-only so final verification does not change runtime behavior.
