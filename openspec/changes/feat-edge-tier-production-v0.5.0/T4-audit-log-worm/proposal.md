# Proposal · T4 audit-log WORM 3 layers

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task group: `T4 · audit-log WORM 3 layers`
> Canonical spec: `../specs/T4-audit-log-worm.spec.md`
> Status: spec-only decomposition for maintainer review

## 1. One Sentence

T4 turns audit logging into a three-layer WORM path: ClickHouse `_audit_log`, deterministic hash chain, and filesystem append-only enforcement.

## 2. Scope

In scope for T4:

- ClickHouse schema and append-only permissions for `_audit_log`.
- Hash-chain pure functions and verification logic.
- ClickHouse writer and fallback writer.
- Audit-log server integration path.
- Filesystem `chattr +a` setup and verification.
- Daily hash-chain verify script and cron-friendly helper.
- Model-router `AuditAdapter` ClickHouse implementation.
- Drill 3 audit replay implementation.
- T4 audit summary and sign-off.

Out of scope for T4:

- New PHI detection logic.
- Desensitize crypto changes.
- Model-router policy changes unrelated to audit emission.
- Cloud KMS integration.
- Non-audit product features.

## 3. Inputs From T3

T4 can rely on T3 outputs:

- `mcp/model-router/server_v2.py` emits structured route audit records.
- `FileAuditAdapter` writes `.audit/routing_log.jsonl` with a stable 17-field record.
- `route_v2` already records allow / deny / circuit / rate / invalid request outcomes.
- `ClickHouseAuditAdapter` is a placeholder and can be replaced in T4.
- `T3.7` / `T3.8` give synthetic bypass and e2e baselines for audit replay.

T4 must not assume:

- ClickHouse WORM is already live.
- Fallback replay is already implemented.
- `mcp/audit-log/server.py` is the runtime target by default.

## 4. Reviewer Decisions Already Accepted

- Accept: unit tests for hash-chain pure functions and writer mocks go into ordinary pytest.
- Accept: ClickHouse integration tests are marked `@pytest.mark.clickhouse` and skipped by default in CI.
- Accept: fallback writer is mandatory.
- Accept with qualification: keep `mcp/audit-log/server.py` as compatibility surface; use `server_v2.py` for the new runtime path.
- Accept: `setup-worm.sh` is cross-platform, with macOS skip behavior and Linux `chattr +a` execution.
- Accept: drill 3 audit replay belongs to T4.9 because hash-chain verify is the core replay primitive.

## 5. Proposed T4 Shape

T4 should be split into 10 leaves:

1. schema DDL + permissions
2. hash-chain pure functions
3. ClickHouse writer
4. file fallback writer
5. audit-log server integration
6. WORM setup script + `lsattr` verification
7. hash-chain verify script + daily cron helper
8. model-router `AuditAdapter` ClickHouse implementation
9. drill 3 audit replay
10. final audit summary + sign-off

## 6. Why This Exists

T4 is the missing persistence layer between T3 routing decisions and T6/T12 replay / compliance checks.

It provides:

- append-only storage semantics,
- tamper-evident hash chaining,
- a fallback when ClickHouse is unavailable,
- a re-verifiable daily integrity check,
- and a stable contract for later audit consumers.

## 7. Storage Model

T4 assumes:

- `event_id`, `timestamp`, actor/action/context/result, `input_hash`, `output_hash`, `prev_hash`, `current_hash` are the canonical audit record fields.
- ClickHouse is the primary WORM store.
- Local fallback JSONL exists only to avoid loss during outage, then backfill.
- File-system append-only is part of the defense-in-depth layer.

## 8. Handoff

T4 hands off to:

- T5 for replayed drill coverage that consumes the hash-chain model.
- T6 for replay-driven compliance and audit workflows.
- T12/T13 for packaging and operational hardening.

## 9. RFC Questions

The following questions need maintainer answers before T4.1 starts.