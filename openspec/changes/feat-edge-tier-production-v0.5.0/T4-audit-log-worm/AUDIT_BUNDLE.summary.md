# T4 · audit-log WORM 3 layers · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T4 · audit-log WORM 3 layers`
> Status: production acceptance met for T4 scope
> Date: 2026-05-24
> Scope: final verification summary only; no code in T4.10

## 1. Change Overview

T4 moved `mcp-audit-log` from a stub concept to a three-layer WORM path: append-only ClickHouse schema, tamper-evident hash chain, and filesystem append-only setup with fallback replay.

T4 implementation leaves completed before this summary:

| Leaf | PR | Merge commit | Leaf commit | One-line result |
|---|---:|---|---|---|
| T4.1 | [#51](https://github.com/charliehzm/medharness/pull/51) | `ed6eddb` | `dba9372` | Added `_audit_log` MergeTree DDL, 21 fields, TTL 7 years, and append-only GRANT/REVOKE. |
| T4.2 | [#52](https://github.com/charliehzm/medharness/pull/52) | `c70cbbe` | `959bd9f` | Added deterministic `canonical_json`, `compute_hash`, `verify_chain`, and GENESIS handling. |
| T4.3 | [#53](https://github.com/charliehzm/medharness/pull/53) | `06c5cb5` | `9691b85` | Added `ClickHouseAuditWriter` with writer-side `row_id`, chain head fetch, insert ordering, and fail-closed writes. |
| T4.4 | [#54](https://github.com/charliehzm/medharness/pull/54) | `0f2c1d7` | `5048573` | Added `FileFallbackWriter`, PID lock, JSONL append, replay iteration, and replay markers. |
| T4.5 | [#55](https://github.com/charliehzm/medharness/pull/55) | `a3b7e1c` | `320dabf` | Added `AuditLogServerV2` NORMAL/FALLBACK/BACKFILL state machine and fixed test namespace isolation. |
| T4.6 | [#56](https://github.com/charliehzm/medharness/pull/56) | `240edb7` | `336971e` | Added `setup-worm.sh` for Linux `chattr +a`, macOS skip, and `lsattr` verification. |
| T4.7 | [#57](https://github.com/charliehzm/medharness/pull/57) | `ab1617f` | `99a6b05` | Added `verify-hashchain.sh` and JSONL verification logic with cron-friendly exit codes. |
| T4.8 | [#58](https://github.com/charliehzm/medharness/pull/58) | `560c42c` | `cd038f4` | Wired `model-router` `ClickHouseAuditAdapter` to `AuditLogServerV2.append()`. |
| T4.9 | [#59](https://github.com/charliehzm/medharness/pull/59) | `faef279` | `26a91ad` | Replaced drill 3 stub with audit replay hash-chain checks and run-all gate. |

T4.10 is this documentation-only verification leaf. It does not change runtime code.

## 2. Compliance Posture

| Redline | Result | Evidence |
|---|---|---|
| R1 PHI never enters raw prompts | YES | T4.1 schema has no prompt or plaintext columns; T4.3 `test_insert_payload_contains_no_prompt_field`; T4.4 rejects `prompt` / `raw_text`; T4.8 sentinel test confirms router raw payload is not mapped into audit events; T4.9 fixture uses only synthetic hashes. |
| R2 models route by allowlist | N/A for T4 runtime; preserved | T4.8 touches only `ClickHouseAuditAdapter`; T3.8 drill 2 still passes inside `tests/red-team-drills/run_all.sh` after T4.9. |
| R3 full audit record | YES for T4 scope | T4.1 schema, T4.2 hash chain, T4.3 ClickHouse writer, T4.4 fallback writer, T4.5 state machine, T4.6 WORM setup, T4.7 verifier, and T4.9 replay drill form the audit evidence path. |
| R4 test data compliance | YES | All T4 tests use synthetic events, `tmp_path`, fake clients, mock writers, or local JSONL fixtures; T4.9 fixture is a 36-row synthetic six-month chain. |
| R5 license permanence | YES | T4.1-T4.10 do not modify `LICENSE`, `NOTICE`, or the Apache 2.0 / CC BY-SA 4.0 commitment. |

R1 details:

- `_audit_log` stores only metadata and hashes: `input_hash` and `output_hash` are `FixedString(64)`.
- `ClickHouseAuditWriter._validate_event` rejects top-level `prompt` and `raw_text`.
- `FileFallbackWriter._validate_event` rejects top-level `prompt` and `raw_text`.
- `ClickHouseAuditAdapter._record_to_event` computes sha256 hashes from routing key fields and does not pass raw prompt payloads.
- T4.9 fixture uses `sha256("synthetic-input-N")` and `sha256("synthetic-output-N")`.

R3 details:

- Layer 1: ClickHouse `_audit_log` is append-only by permissions and ordered by `(timestamp, row_id)`.
- Layer 2: every row links to the previous `current_hash`, with `row_id` included in canonical JSON.
- Layer 3: `_audit_log`, `audit-export`, and `audit-backup` directories are prepared for filesystem append-only mode on Linux.
- Outage path: fallback JSONL keeps `prev_hash`, `current_hash`, and `row_id` so backfill is replayable.
- Detection path: daily verify script and drill 3 both detect row and genesis tampering.

## 3. Implementation Summary

### 3.1 T4.1 · ClickHouse schema DDL + permissions

- PR: [#51](https://github.com/charliehzm/medharness/pull/51)
- Merge commit: `ed6eddb`
- Leaf commit: `dba9372`
- Key files: `mcp/audit-log/sql/audit_log.sql`, `tests/test_audit_log_schema.py`
- LOC: 2 files, 167 insertions.
- Tests: 3.
- Delivered `_audit_log` schema with actor, action, context, result, hashes, `row_id`, and `inserted_at`.
- Delivered `MergeTree`, `PARTITION BY toYYYYMM(timestamp)`, `ORDER BY (timestamp, row_id)`, and `TTL timestamp + INTERVAL 7 YEAR`.
- Delivered writer permissions: `GRANT INSERT, SELECT` and `REVOKE ALTER UPDATE, ALTER DELETE`.

### 3.2 T4.2 · hashchain pure functions

- PR: [#52](https://github.com/charliehzm/medharness/pull/52)
- Merge commit: `c70cbbe`
- Leaf commit: `959bd9f`
- Key files: `mcp/audit-log/hashchain.py`, `tests/test_hashchain.py`
- LOC: 2 files, 238 insertions.
- Tests: 10.
- Delivered `GENESIS_PREV_HASH = "GENESIS"` and legacy all-zero compatibility.
- Delivered canonical compact JSON with sorted keys and required-field validation.
- Delivered `compute_hash(event, prev_hash)` as `sha256(canonical_json(event_with_row_id) + "|" + prev_hash)`.
- Delivered `verify_chain(rows)` returning `(ok, broken_at_row_id_or_None)`.

### 3.3 T4.3 · ClickHouseAuditWriter

- PR: [#53](https://github.com/charliehzm/medharness/pull/53)
- Merge commit: `06c5cb5`
- Leaf commit: `9691b85`
- Key files: `mcp/audit-log/clickhouse_writer.py`, `tests/test_audit_log_writer.py`
- LOC: 2 files, 445 insertions.
- Tests: 10.
- Delivered lazy `clickhouse_connect.get_client` import inside `_default_client_factory`.
- Delivered startup `SELECT current_hash ... LIMIT 1` and `SELECT max(row_id)`.
- Delivered writer-side monotonic `row_id` assignment.
- Delivered fail-closed behavior: invalid events raise `WriterContract`; insert failures raise `ClickHouseUnavailable`; chain head advances only after insert success.

### 3.4 T4.4 · FileFallbackWriter

- PR: [#54](https://github.com/charliehzm/medharness/pull/54)
- Merge commit: `0f2c1d7`
- Leaf commit: `5048573`
- Key files: `mcp/audit-log/fallback_writer.py`, `tests/test_audit_log_fallback.py`
- LOC: 2 files, 259 insertions.
- Tests: 13.
- Delivered base directory creation and `fallback.pid` PID lock.
- Delivered `audit-fallback-<ts>.jsonl` append path.
- Delivered required chain fields: `event_id`, `row_id`, `prev_hash`, `current_hash`.
- Delivered `list_pending`, `replay_iter`, `mark_replayed`, and idempotent `release_lock`.

### 3.5 T4.5 · AuditLogServerV2 state machine

- PR: [#55](https://github.com/charliehzm/medharness/pull/55)
- Merge commit: `a3b7e1c`
- Leaf commit: `320dabf`
- Key files: `mcp/audit-log/server_v2.py`, `tests/test_audit_log_server_v2.py`
- LOC: merge includes 2 files, 565 insertions.
- Tests: 14.
- Delivered `ServerState.NORMAL`, `FALLBACK`, and `BACKFILL`.
- Delivered append routing to ClickHouse in NORMAL and fallback JSONL on `ClickHouseUnavailable`.
- Delivered `recover()` replay from fallback files into ClickHouse and `mark_replayed` protection.
- Delivered `health`, `query`, `verify`, and `seal_bundle` placeholders for later integration.
- Review regression fix: tests use an isolated module namespace to avoid `server_v2` collisions with T2.

### 3.6 T4.6 · setup-worm.sh + lsattr verification

- PR: [#56](https://github.com/charliehzm/medharness/pull/56)
- Merge commit: `240edb7`
- Leaf commit: `336971e`
- Key files: `scripts/setup-worm.sh`, `tests/test_setup_worm.py`
- LOC: 2 files, 199 insertions.
- Tests: 9.
- Delivered strict bash mode, OS detection, and `MEDHARNESS_AUDIT_BASE` override.
- Delivered three managed directories: `_audit_log`, `audit-export`, and `audit-backup`.
- Linux path runs `sudo chattr +a` and verifies with `lsattr -d`.
- macOS path creates directories and warns that production WORM enforcement requires Linux.

### 3.7 T4.7 · verify-hashchain.sh + verify_hashchain_logic.py

- PR: [#57](https://github.com/charliehzm/medharness/pull/57)
- Merge commit: `ab1617f`
- Leaf commit: `99a6b05`
- Key files: `scripts/verify-hashchain.sh`, `scripts/verify_hashchain_logic.py`, `tests/test_verify_hashchain.py`
- LOC: 3 files, 309 insertions.
- Tests: 11.
- Delivered shell wrapper with Python detection and input override.
- Delivered JSONL verification logic that calls T4.2 `verify_chain`.
- Exit codes: `0` intact, `1` tampered, `2` missing input, `3` invalid JSONL, `4` Python missing.
- Output is structured JSON with `status`, `row_count`, `broken_at_row_id`, and `passed`.

### 3.8 T4.8 · model-router ClickHouseAuditAdapter

- PR: [#58](https://github.com/charliehzm/medharness/pull/58)
- Merge commit: `560c42c`
- Leaf commit: `cd038f4`
- Key files: `mcp/model-router/server_v2.py`, `tests/test_model_router_server_v2.py`
- LOC: 2 files, 205 insertions, 6 deletions.
- Tests: 6 new adapter tests; full file now 14 tests.
- Delivered explicit injection contract: default construction raises `NotImplementedError`; callers must pass `audit_server` or `audit_server_factory`.
- Delivered T3 routing record to T4 audit event mapping.
- Delivered delegation only through `AuditLogServerV2.append()`.
- Delivered raw-payload sentinel test.

### 3.9 T4.9 · drill 3 audit replay

- PR: [#59](https://github.com/charliehzm/medharness/pull/59)
- Merge commit: `faef279`
- Leaf commit: `26a91ad`
- Key files: `tests/red-team-drills/drill_audit_replay.py`, `tests/red-team-drills/fixtures/audit_replay_bundle.jsonl`, `tests/red-team-drills/run_all.sh`
- LOC: 3 files, 191 insertions, 6 deletions.
- Cases: 3.
- Delivered a 36-row synthetic chain spanning January through June 2026.
- Delivered `intact-chain`, `tampered-mid-row`, and `tampered-genesis` cases.
- Delivered `run_all.sh` drill 3 gate for `passed`, `chain_intact`, and `tampered_detected`.

## 4. ADR-03 + T4 Q&A Alignment

T4 implements `openspec/changes/feat-edge-tier-production-v0.5.0/design.md` ADR-03 T4 subsection.

Main ADR-03 decision:

- Audit evidence is protected by three WORM layers: database append-only permissions, hash-chain tamper evidence, and filesystem append-only protection.
- ClickHouse is the target append-only audit store for v0.5.0 edge-tier production.
- Fallback JSONL is mandatory so a ClickHouse outage does not erase audit evidence.

ADR-03 Q1:

- Decision: use `clickhouse-connect`, which is HTTP deployment friendly.
- Implementation: T4.3 `_default_client_factory` imports `clickhouse_connect.get_client` lazily.
- Evidence: T4.3 unit tests inject fake client factories and do not require a live ClickHouse server.

ADR-03 Q2:

- Decision: `current_hash = sha256(canonical_json(event_with_row_id) + "|" + prev_hash)`.
- Implementation: T4.2 `compute_hash` uses `f"{canonical}|{prev_hash}".encode()`.
- Evidence: T4.2 deterministic and tamper tests; T4.9 drill detects mid-row mutation.

ADR-03 Q3:

- Decision: preserve the original chain through fallback with PID lock and a recovery backfill state machine.
- Implementation: T4.4 writes `prev_hash`, `current_hash`, and `row_id`; T4.5 preserves fallback hashes during direct backfill insert.
- Evidence: T4.5 `test_chain_head_continuity_across_normal_to_fallback_transition` and recover tests.

ADR-03 Q4:

- Decision: T4.9 verifies hash-chain integrity only; semantic replay is deferred to T6/v0.6+.
- Implementation: T4.9 calls `scripts/verify_hashchain_logic.py` and reports intact/tampered outcomes.
- Evidence: T4.9 cases `intact-chain`, `tampered-mid-row`, and `tampered-genesis`.

ADR-03 Q5:

- Decision: writer owns monotonic `row_id` generation.
- Implementation: T4.3 fetches max `row_id` at startup and increments in memory on successful append.
- Evidence: T4.3 empty-table, existing-data, and failure-does-not-advance tests.

ADR-03 Q6:

- Decision: all three directories are managed: `_audit_log`, `audit-export`, and `audit-backup`.
- Implementation: T4.6 `DIRS` contains all three under `MEDHARNESS_AUDIT_BASE`.
- Evidence: T4.6 tests assert all three names and env override behavior.

## 5. Threat Model + Mitigations

| Threat class | Attack path | Mitigation | Evidence |
|---|---|---|---|
| Database row tamper | Attacker mutates a stored audit row while leaving row count unchanged | Hash chain recomputes canonical event plus prior hash and detects first broken `row_id` | T4.2 tamper test; T4.7 tampered-chain test; T4.9 `tampered-mid-row` broken_at `18` |
| Database row delete | Attacker deletes old audit rows from `_audit_log` | Writer has only INSERT and SELECT; ALTER UPDATE / DELETE are revoked | T4.1 DDL and tests assert GRANT/REVOKE clauses |
| File-layer delete or mutation | Attacker removes ClickHouse parts, export files, or backups | Linux setup applies `chattr +a` to `_audit_log`, `audit-export`, and `audit-backup` | T4.6 script and tests |
| ClickHouse service outage | Primary audit store is unavailable during a tool or model action | Server transitions to FALLBACK and writes replayable JSONL | T4.4 writer; T4.5 NORMAL -> FALLBACK tests |
| Fallback PHI leak | Fallback JSONL accidentally stores a raw prompt or response | Fallback writer rejects top-level `prompt` and `raw_text` | T4.4 contract tests |
| Concurrent fallback writers | Two local processes append fallback files at the same time | `fallback.pid` PID lock rejects a second writer when the first PID is alive | T4.4 lock-held test |
| Multi-writer `row_id` race | Multiple server instances assign the same `row_id` | v0.5.0 assumes a single writer instance with startup max-row fetch and in-memory counter | T4.3 design; residual risk documented in section 10 |
| Hash-chain replay or row reorder | Attacker reorders rows or replays a segment with valid row hashes | `row_id` is part of canonical JSON and verification orders by rows supplied from export | T4.2 required fields and T4.7/T4.9 verification |
| Chain verification delay | Tamper occurs after insert but before a human checks evidence | `verify-hashchain.sh` is cron-friendly and exits non-zero on tamper for SEV-1 routing | T4.7 shell wrapper and exit-code tests |
| Router audit boundary bypass | Model-router writes somewhere other than the T4 audit chain | `ClickHouseAuditAdapter` delegates only to `AuditLogServerV2.append()` | T4.8 adapter tests |

Residual note: v0.5.0 does not yet run a real ClickHouse container in CI. Database permissions and client insert behavior are unit-tested by SQL parsing and mocks, with real integration deferred.

## 6. Test Coverage Matrix

Final T4 verification baseline:

- Full repository tests: `178 passed, 1 skipped`.
- Red-team drill wrapper: `4` drills invoked by `tests/red-team-drills/run_all.sh`.
- Drill 1: PHI recall real gate.
- Drill 2: model-router bypass real gate with 11 cases.
- Drill 3: audit replay real gate with 3 cases.
- Drill 4: prompt injection still a structured stub; implementation belongs to T7.
- T4-focused unit tests and drill cases: 76 by accepted leaf accounting.

| Leaf | Test file or drill | Count | Coverage |
|---|---|---:|---|
| T4.1 | `tests/test_audit_log_schema.py` | 3 | DDL fields, engine, partition, order, TTL, GRANT/REVOKE, no prompt columns |
| T4.2 | `tests/test_hashchain.py` | 10 | GENESIS, determinism, event/prev changes, field order, 100-row verify, tamper, missing fields |
| T4.3 | `tests/test_audit_log_writer.py` | 10 | startup state, client/query failures, append envelope, fail-closed, column order, no prompt payload |
| T4.4 | `tests/test_audit_log_fallback.py` | 13 | base dir, PID lock, stale lock, append, validation, pending list, replay, marker, lock release |
| T4.5 | `tests/test_audit_log_server_v2.py` | 14 | startup states, append paths, fallback, backfill, recover failure, health, no prompt, chain continuity |
| T4.6 | `tests/test_setup_worm.py` | 9 | shebang, macOS skip, Linux root skip/real path, dirs, env override, strict mode, exit codes |
| T4.7 | `tests/test_verify_hashchain.py` | 11 | intact, tampered, missing input, invalid JSON, empty file, report, shell wrapper, env override |
| T4.8 | `tests/test_model_router_server_v2.py` new tests | 6 | adapter injection, factory, delegation, mapping, no raw payload leak |
| T4.9 | `drill_audit_replay.py` | 3 cases | intact chain, tampered mid-row, tampered genesis |

Drill 3 fixture:

- File: `tests/red-team-drills/fixtures/audit_replay_bundle.jsonl`.
- Row count: 36.
- Time span: 2026-01 through 2026-06.
- Actors: synthetic coder, reviewer, and compliance roles.
- Actions: synthetic model-router, phi-detector, and desensitize events.
- Case results: `intact-chain` passes, `tampered-mid-row` fails at row `18`, `tampered-genesis` fails at row `0`.

## 7. Audit Event Schema

T4.1 `_audit_log` columns:

| Column | Type | Notes |
|---|---|---|
| `event_id` | `UUID` | stable event identifier |
| `timestamp` | `DateTime64(3, 'UTC')` | event time |
| `actor_agent_role` | `LowCardinality(String)` | coder / reviewer / compliance / other role |
| `actor_model_id` | `String` | full model id |
| `actor_vendor_family` | `LowCardinality(String)` | vendor family |
| `actor_session_id` | `String` | session id |
| `action_tool` | `String` | MCP/tool name |
| `action_skill` | `Nullable(String)` | optional Skill name |
| `action_operation` | `LowCardinality(String)` | route / detect / desensitize / read / write |
| `context_change_id` | `Nullable(String)` | OpenSpec change id |
| `context_step` | `Nullable(UInt8)` | SOP step |
| `context_data_levels` | `Array(LowCardinality(String))` | one event can touch multiple data levels |
| `result_status` | `LowCardinality(String)` | success / blocked / error / route decision |
| `result_reason` | `Nullable(String)` | safe reason string |
| `result_duration_ms` | `Float32` | event duration |
| `input_hash` | `FixedString(64)` | sha256 hex of input representation |
| `output_hash` | `FixedString(64)` | sha256 hex of output representation |
| `prev_hash` | `FixedString(64)` | previous row hash |
| `current_hash` | `FixedString(64)` | current row hash |
| `row_id` | `UInt64` | writer-generated monotonic row id |
| `inserted_at` | `DateTime64(3) DEFAULT now64()` | ClickHouse insertion time |

Schema decisions:

- `LowCardinality(String)` is used where value sets are expected to be small.
- `Nullable` is used for optional fields rather than sentinel strings.
- All hash fields are `FixedString(64)` because sha256 hex has 64 characters.
- `row_id` is generated by the writer per ADR-03 Q5 and participates in hash canonicalization.
- `inserted_at` is omitted from writer `COLUMN_ORDER` and filled by ClickHouse `DEFAULT now64()`.
- No prompt, raw input, raw output, or PHI plaintext column exists.

## 8. State Machine

T4.5 `AuditLogServerV2` has three states:

| State | Writer path | Writes accepted | Purpose |
|---|---|---|---|
| `NORMAL` | `ClickHouseAuditWriter.append()` | yes | primary ClickHouse audit append |
| `FALLBACK` | server computes chain fields, then `FileFallbackWriter.append()` | yes | durable local outage path |
| `BACKFILL` | direct ClickHouse insert of fallback rows | no | replay pending fallback files without interleaving new writes |

Transition matrix:

| From | Trigger | To | Evidence |
|---|---|---|---|
| startup | ClickHouse writer initializes | `NORMAL` | T4.5 startup available test |
| startup | ClickHouse writer raises `ClickHouseUnavailable` | `FALLBACK` | T4.5 startup unavailable test |
| `NORMAL` | append raises `ClickHouseUnavailable` | `FALLBACK` | T4.5 append failure switch test |
| `FALLBACK` | `recover()` called and ClickHouse still unavailable | `FALLBACK` | T4.5 recover failure test |
| `FALLBACK` | `recover()` reinitializes ClickHouse | `BACKFILL` | T4.5 recover replay test |
| `BACKFILL` | all pending files replay and marked | `NORMAL` | T4.5 recover replay test |
| `BACKFILL` | append attempted | error | T4.5 backfill pause test |

Chain continuity:

- Server holds `_last_hash` and `_next_row_id` across NORMAL -> FALLBACK.
- Fallback events persist caller-provided `prev_hash`, `current_hash`, and `row_id`.
- Backfill preserves fallback hashes instead of recomputing with `ClickHouseAuditWriter.append()`.
- After successful backfill, server re-syncs chain head from ClickHouse.
- `recover()` checks whether `<file>.replayed` already exists before calling `mark_replayed`.

## 9. Performance Profile

Measured in T4 local verification:

- T4.7 verification logic handles 100-row synthetic chains in unit tests.
- T4.9 drill verifies the 36-row six-month fixture plus two tampered variants through subprocess calls in `run_all.sh`.
- Full repository tests after T4.9: `178 passed, 1 skipped in 4.66s`.

Expected production profile:

- Spec target C1: one audit write p99 < 50 ms.
- Spec target C2: >= 1000 events/sec on one ClickHouse node.
- T4.3 writer uses single-row `client.insert` and mock tests only; no real ClickHouse throughput benchmark was run in T4.
- T4.7 verify is cron-oriented and not on the request hot path.

Deferred benchmark:

- Production insert benchmark is deferred to real ClickHouse integration work in T6/T13.
- The benchmark should include `clickhouse-connect`, async insert options if enabled later, fallback latency under outage, and verify runtime on a full audit export.

## 10. Known Limitations + Follow-ups

1. `ClickHouseAuditWriter._required_event_fields(event)` accepts `event` but does not use it; minor style cleanup can remove the unused parameter later.
2. `FileFallbackWriter.mark_replayed()` itself is not idempotent; T4.5 guards it before calling, but the writer API could become safer.
3. `FileFallbackWriter._pid_alive()` treats `PermissionError` as not alive; that is conservative but could misclassify on unusual local permission boundaries.
4. `FileFallbackWriter._acquire_lock()` is not atomic; v0.5.0 assumes one local server process, but atomic file locking is a future hardening task.
5. `AuditLogServerV2.recover()` leaves the server in `BACKFILL` if direct insert fails; this is fail-loud by design but needs operator runbook coverage.
6. Legacy `mcp/audit-log/server.py` remains a stub compatibility surface; v0.6 can decide whether to shim or retire it.
7. `setup-worm.sh` checks whether `lsattr` output contains `a`; Linux attr characters should make this safe, but a stricter positional parser would be cleaner.
8. T4.8 maps `result.reason` into the audit event; router reasons are currently synthetic and PHI-free, but future callers must keep reason strings safe.
9. T4.9 fixture has 36 rows across six months; it is enough for replay smoke coverage, not for scale or density simulation.
10. T4.9 does not cover non-contiguous `row_id`, duplicate `row_id`, or out-of-order export edge cases.
11. `clickhouse-connect` real `client.insert` behavior is mock-tested only; true server integration still needs a containerized ClickHouse run.
12. Drill 4 prompt injection remains a structured stub; ownership belongs to T7.
13. WORM physical enforcement is skipped on macOS development machines; only Linux production exercises `chattr +a`.
14. Fallback file retention, encryption at rest, and cleanup policy are not implemented in T4.
15. No SEV-1 PagerDuty or Slack integration is wired; T4.7 exits non-zero and prints alert text for external monitoring.

## 11. Handoff Notes

T4 -> T5 drill enhancements:

- Implement drill 4 prompt injection contract and gate.
- Expand drill 3 from hash-only replay to richer tamper patterns if needed.
- Keep drill outputs machine-readable and gateable through `run_all.sh`.

T4 -> T6 integration:

- Start a real ClickHouse container for integration tests.
- Exercise `ClickHouseAuditWriter` against real `_audit_log`.
- Wire `AuditLogServerV2.verify()` to `scripts/verify-hashchain.sh`.
- Validate recovery/backfill with real ClickHouse inserts.

T4 -> T12 backup/recovery:

- Implement `audit-backup/` backup scripts and retention.
- Define fallback JSONL retention and cleanup after backfill.
- Ensure `audit-export/` and `audit-backup/` inherit WORM setup in install paths.

T4 -> T13 offline build:

- Add `clickhouse-connect` to `requirements.txt` or offline dependency bundle when runtime deployment is enabled.
- Include ClickHouse server 24.x container image in the offline tarball if ClickHouse is packaged locally.
- Hook `scripts/setup-worm.sh` into install/bootstrap flow.

T4 -> T18-T20 compliance documents:

- Document HIPAA 6-year retention and the 7-year TTL buffer.
- Document PIPL data-localization posture for audit metadata and exports.
- Document regulator audit-log export flow, replay procedure, and hash-chain evidence format.

## 12. Sign-off (4 方)

| Signer | Status | Evidence |
|---|---|---|
| codex Coder-Agent | ✅ complete | T4.1-T4.9 leaves implemented and merged; T4.10 summary prepared. |
| Claude Reviewer-Agent (异构) | ✅ complete | Each T4 leaf PR passed review and was merged before this summary. |
| Compliance-Agent (异构) | ✅ complete | R1-R5 evidence is cited above; no raw PHI storage path is introduced. |
| Maintainer (`charliehzm`) | ⏳ pending | This T4.10 PR is the maintainer review and final sign-off vehicle. |
