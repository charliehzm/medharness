# T4 · audit-log WORM 3 layers · leaf task plan

> Parent task group: `T4 · audit-log WORM 3 layers`
> Parent task list: `../tasks.md`
> Architecture decision target: pending maintainer ADR entry in `../design.md` after RFC answers
> Canonical spec: `../specs/T4-audit-log-worm.spec.md`
> Branch model: each leaf starts from `main` as `feat/T4.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 substantive files.
- 3 files are allowed only when the 3rd file is wiring-only, <= 15 changed lines, and necessary.
- 4+ files must be split.
- T4 must not delete the current `mcp/audit-log/server.py` compatibility surface without an explicit RFC answer.
- T4 should introduce the new runtime path in `mcp/audit-log/server_v2.py`.
- T4.5 may touch a third file only when `mcp/audit-log/server.py` is a wiring-only compatibility shim with <= 15 changed lines.
- Unit tests for hash-chain logic and writer mocks go into ordinary pytest.
- ClickHouse integration tests must be marked `@pytest.mark.clickhouse` and skipped by default in CI.
- `--full` or a local integration run may opt into ClickHouse tests.
- Fallback writer is mandatory.
- ClickHouse outage must write `audit-fallback-<ts>.jsonl` and preserve replayability.
- `setup-worm.sh` must be cross-platform: macOS skips real `chattr`, Linux runs it.
- Drill 3 audit replay belongs to T4.9 because hash-chain verify is the replay primitive.
- T4 must keep audit content free of raw prompt text.

## Runtime Contract

T4 enforces a three-layer WORM path:

1. ClickHouse `_audit_log` table is append-only with restricted grants.
2. Hash chain makes every row tamper-evident.
3. Filesystem append-only mode reduces deletion and mutation risk.

Failure mode is always fail-loud:

- ClickHouse unavailable -> write fallback JSONL.
- Hash-chain broken -> verify fails and alerts.
- `chattr` setup failure -> install/setup fails fast.

## Leaf Sub-tasks

### T4.1 · ClickHouse schema DDL + permissions

- Branch: `feat/T4.1-audit-schema`
- Files:
  - `mcp/audit-log/sql/audit_log.sql`
  - `tests/test_audit_log_schema.py`
- Scope:
  - Define `_audit_log` DDL, TTL, partitioning, ordering, and grant / revoke rules.
  - Preserve append-only semantics and 6-year retention buffer.
  - Ensure schema matches the canonical audit_event shape from the spec.
- Acceptance:
  - `CREATE TABLE`, `GRANT`, and `REVOKE` text is present and parseable.
  - No UPDATE / DELETE permissions are granted.
  - Fields map cleanly to actor / action / context / result / hash columns.
  - No raw prompt text appears in schema comments or tests.

### T4.2 · hashchain pure functions

- Branch: `feat/T4.2-hashchain-core`
- Files:
  - `mcp/audit-log/hashchain.py`
  - `tests/test_hashchain.py`
- Scope:
  - Implement GENESIS handling, canonical serialization, `compute_hash`, and chain verification.
  - Keep logic deterministic and side-effect free.
  - Make the canonical representation explicit for audit replay.
- Acceptance:
  - 100-line synthetic chain verifies.
  - One tampered row breaks the chain.
  - GENESIS behavior is stable and documented.
  - Hash computation is deterministic across repeated runs.

### T4.3 · ClickHouseAuditWriter

- Branch: `feat/T4.3-clickhouse-writer`
- Files:
  - `mcp/audit-log/clickhouse_writer.py`
  - `tests/test_audit_log_writer.py`
- Scope:
  - Wrap the ClickHouse client and append audit rows.
  - Fetch the last hash on startup.
  - Assign or persist monotonic row ordering as required by the final RFC answer.
  - Keep insert path fail-closed and audit-safe.
- Acceptance:
  - Writer appends rows with `prev_hash` and `current_hash`.
  - Startup fetches the last known chain head.
  - Rejected writes do not mutate the chain.
  - No raw prompt text enters the insert payload.

### T4.4 · FileFallbackWriter

- Branch: `feat/T4.4-file-fallback-writer`
- Files:
  - `mcp/audit-log/fallback_writer.py`
  - `tests/test_audit_log_fallback.py`
- Scope:
  - Write `audit-fallback-<ts>.jsonl` when ClickHouse is unavailable.
  - Preserve enough metadata to backfill later.
  - Expose a replay-friendly batch format.
  - Backfill pending fallback files when ClickHouse recovers, following the RFC answer for chain continuity.
- Acceptance:
  - ClickHouse outage writes fallback JSONL.
  - Fallback entries keep chain context.
  - Backfill data remains synthetic-safe and replayable.

### T4.5 · audit-log server integration

- Branch: `feat/T4.5-audit-server-v2`
- Files:
  - `mcp/audit-log/server_v2.py`
  - `tests/test_audit_log_server_v2.py`
  - `mcp/audit-log/server.py` (wiring-only shim, if needed)
- Scope:
  - Move the runtime audit path onto the new implementation surface.
  - Keep CLI and stdio methods compatible.
  - Route to ClickHouse writer first, fallback writer on outage.
  - Preserve the legacy `server.py` compatibility surface.
- Acceptance:
  - `append`, `query`, `verify`, `seal_bundle`, and `health` remain callable.
  - ClickHouse failure uses fallback writer.
  - Hash-chain fields are emitted in order.
  - No raw prompt text appears in responses.

### T4.6 · setup-worm.sh + lsattr verification

- Branch: `feat/T4.6-worm-setup`
- Files:
  - `scripts/setup-worm.sh`
  - `tests/test_setup_worm.py`
- Scope:
  - Detect OS and choose the right append-only behavior.
  - Run real `chattr +a` on Linux.
  - Skip unsupported append-only enforcement on macOS while still verifying tooling availability.
- Acceptance:
  - Linux path applies `chattr +a`.
  - macOS path skips real `chattr` cleanly.
  - `lsattr` verification is explicit.
  - Setup failures fail fast.

### T4.7 · verify-hashchain.sh + verify_hashchain_logic.py

- Branch: `feat/T4.7-hashchain-verify`
- Files:
  - `scripts/verify-hashchain.sh`
  - `scripts/verify_hashchain_logic.py`
- Scope:
  - Implement daily chain verification and alert-friendly exit codes.
  - Recompute hashes from exported rows.
  - Surface tamper evidence clearly.
- Acceptance:
  - Good chain exits 0.
  - Tampered chain exits non-zero.
  - Cron-friendly script path is explicit.
  - Verification logic is deterministic.

### T4.8 · model-router AuditAdapter ClickHouse implementation

- Branch: `feat/T4.8-router-audit-adapter`
- Files:
  - `mcp/model-router/server_v2.py`
  - `tests/test_model_router_server_v2.py`
- Scope:
  - Replace the `ClickHouseAuditAdapter` placeholder with a real implementation.
  - Keep file audit fallback semantics aligned with T4.4.
  - Preserve the T3 route contract and audit fields.
- Acceptance:
  - Placeholder `NotImplementedError` is removed.
  - Audit writes are routed through the T4 adapter.
  - T3 route behavior stays fail-closed.
  - Audit records remain free of raw prompt text.

### T4.9 · drill 3 audit replay

- Branch: `feat/T4.9-audit-replay-drill`
- Files:
  - `tests/red-team-drills/drill_audit_replay.py`
  - `tests/red-team-drills/fixtures/audit_replay_bundle.jsonl`
- Scope:
  - Replace the stub with replayable audit integrity checks.
  - Re-use six-month synthetic fixture data and chain verification.
  - Validate that replay can detect chain or content drift.
- Acceptance:
  - Replay report is structured and machine-readable.
  - Hash-chain failures are surfaced.
  - Replay stays synthetic and does not require real PHI.

### T4.10 · T4 final verification and audit summary

- Branch: `feat/T4.10-audit-verify`
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T4-audit-log-worm/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T4-audit-log-worm/tasks.md`
- Scope:
  - Record final T4 verification numbers after T4.1-T4.9 are merged.
  - Mark T4 leaf tasks complete with PRs, commits, commands, and residual risks.
  - Include R1-R5 self-check and T4 -> T5/T6/T12 handoff notes.
- Acceptance:
  - Summary includes schema, hash chain, fallback, setup, replay, and adapter status.
  - `tasks.md` has completion sign-off block.
  - No code changes.

## Dependency Order

```text
T4.1 -> T4.2 -> T4.3 -> T4.4 -> T4.5 -> T4.8 -> T4.10
                   \-> T4.6 -> T4.7 -> T4.10
                   \-> T4.9 -> T4.10
```

## Verification Commands Per Leaf

Run the relevant subset for every leaf:

```bash
ruff check .
pytest tests/
bash dryrun_e2e_v2.sh --ci
```

For T4 leaves that touch ClickHouse or WORM runtime behavior, also run:

```bash
pytest tests/ -m clickhouse -q
bash scripts/setup-worm.sh
bash scripts/verify-hashchain.sh
```

For T4.9 and later, also verify:

```bash
python tests/red-team-drills/drill_audit_replay.py --out tests/red-team-drills/output/audit_replay.json
```

## Open RFC Questions

Q1. Should T4 use `clickhouse-driver` or `clickhouse-connect` as the canonical client for the writer and integration tests?

Q2. Should the chain formula be `sha256(canonical_json + "|" + prev_hash)` or `sha256(canonical_json + prev_hash)`, and should `row_id` or `timestamp` be included in the hash input?

Q3. When ClickHouse recovers after fallback, should backfill preserve the original chain exactly or append a bridge record that re-anchors the fallback segment?

Q4. Should drill 3 audit replay verify only hash-chain integrity, or also replay the stored six-month fixture semantically and compare deterministic outputs?

Q5. Who owns monotonic `row_id` generation for `_audit_log`: client-side writer sequencing or ClickHouse-side assignment?

Q6. For `setup-worm.sh`, should Linux `chattr +a` apply only to `_audit_log` data directories, or also to export and backup directories?