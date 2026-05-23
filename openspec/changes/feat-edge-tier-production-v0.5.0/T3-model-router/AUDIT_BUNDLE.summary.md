# T3 · model-router runtime gate · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T3 · model-router runtime gate`
> Status: production acceptance met for T3 scope
> Date: 2026-05-23
> Scope: final verification summary only; no code in T3.9

## 1. Change Overview

T3 moved `mcp-model-router` from policy-by-description to a runtime gate that fails closed before any model route is allowed.

The gate now enforces ADR-04:

1. Target model must be present in the active `MODEL_ALLOWLIST.json`.
2. Caller role and target vendor family must satisfy the heterogeneous runtime matrix.
3. Requested data level must be allowed by the target model entry.
4. `metadata.desensitized` must be true, proving the prompt path has passed through T2 desensitize first.
5. Denies are dropped, never rerouted to a fallback model.
6. Every allow or deny writes an audit-ready file record for T4 handoff.

T3 implementation leaves completed before this summary:

| Leaf | PR | Merge commit | Leaf commit | One-line result |
|---|---:|---|---|---|
| T3.1 | [#40](https://github.com/charliehzm/medharness/pull/40) | `378807c` | `f2b7ee2` | Added `vendor_families.yml` and strict vendor-family loader. |
| T3.2 | [#41](https://github.com/charliehzm/medharness/pull/41) | `53fce6a` | `56b84bd` | Added list-based `MODEL_ALLOWLIST.json` schema and `HotAllowlist`. |
| T3.3 | [#42](https://github.com/charliehzm/medharness/pull/42) | `dfb49de` | `ef7ace4` | Added pure `PolicyCore` with marker, allowlist, role, data-level, and heterogeneity hook. |
| T3.4 | [#43](https://github.com/charliehzm/medharness/pull/43) | `2ea637f` | `adde388` | Added `HeterogeneityPolicy` and role x vendor-family matrix. |
| T3.5 | [#44](https://github.com/charliehzm/medharness/pull/44) | `069599d` | `cfd3f32` | Added bounded in-memory `CircuitBreaker` and `RateLimiter`. |
| T3.6 | [#45](https://github.com/charliehzm/medharness/pull/45) | `794a710` | `662caf5` | Integrated `server_v2.py` route, stdio, health, audit adapter, limits, and policy. |
| T3.7 | [#46](https://github.com/charliehzm/medharness/pull/46) | `887d232` | `484b2d9` | Added subprocess and stdio router integration tests with synthetic allowlists. |
| T3.8 | [#47](https://github.com/charliehzm/medharness/pull/47) | `aba1860` | `228829d` | Replaced router bypass stub with 11-case drill 2 and `run_all.sh` gate. |

T3.9 is this documentation-only verification leaf. It does not change runtime code.

## 2. Compliance Posture

| Redline | Result | Evidence |
|---|---|---|
| R1 PHI never enters raw prompts | YES | T3.3 `test_reason_is_auditable_and_contains_no_raw_phi`; T3.6 audit tests assert `prompt` and synthetic raw sentinels are not written; T3.7 integration tests assert audit JSONL excludes raw payload strings. |
| R2 models route by allowlist | YES | T3.2 `load_allowlist`; T3.3 `PolicyCore`; T3.6 route flow denies allowlist misses; T3.8 drill cases `direct-openai-endpoint`, `direct-anthropic-endpoint`, and `openrouter-bypass` deny. |
| R3 full audit record | YES for v0.5 file adapter | T3.6 `AuditAdapter` and `FileAuditAdapter` append `.audit/routing_log.jsonl`; `_audit_record` has 17 fields; ClickHouse adapter remains T4 placeholder. |
| R4 test data compliance | YES | T3.7 fixture contains synthetic private deployments only; T3.8 creates temporary synthetic allowlists and never calls a real endpoint. |
| R5 license permanence | YES | T3.1-T3.9 do not modify `LICENSE`, `NOTICE`, or open-source commitment docs. |

R1 details:

- `RouteRequest` carries metadata and route descriptors, not prompt text.
- `server_v2.route_v2` ignores extra `prompt` payload fields when building audit records.
- `tests/test_model_router_server_v2.py` passes `RAW-PHI-CLAIM` as a sentinel and asserts it does not enter `.audit/routing_log.jsonl`.
- `tests/test_model_router_integration.py` passes `SYNTHETIC-RAW-PAYLOAD-SHOULD-NOT-ENTER-AUDIT` and asserts it is absent from audit JSONL.

R2 details:

- T3.2 schema requires each model entry to include `id`, `vendor_family`, `deployment`, `allowed_agent_roles`, `allowed_data_levels`, and `rate_limit_qps`.
- T3.2 cross-validates each `vendor_family` against `vendor_families.yml`.
- T3.6 route checks allowlist loading before rate and policy evaluation.
- T3.8 drill rejects public direct model ids not in the active allowlist.

R3 details:

- T3.6 writes both allow and deny decisions.
- Deny records include `layer_failed`, `severity`, and `error_type`.
- Repeated rejects can escalate to `SEV-2` once the circuit opens.
- T4 still owns WORM ClickHouse `_audit_log`; T3 supplies the adapter boundary.

R4 details:

- T3.7 fixture endpoints are `private://...`, not live URLs.
- T3.8 uses `tempfile.TemporaryDirectory` and writes local allowlists under synthetic `change_id` paths.
- No API key, customer endpoint, real PHI, or real model call appears in T3 tests.

R5 details:

- No license file was touched by T3.
- T3 implementation remains under the existing Apache 2.0 / CC BY-SA 4.0 project split.

## 3. Implementation Summary

### 3.1 T3.1 · vendor families

- PR: [#40](https://github.com/charliehzm/medharness/pull/40)
- Merge commit: `378807c`
- Leaf commit: `f2b7ee2`
- Key files: `mcp/model-router/vendor_families.yml`, `mcp/model-router/vendor_families.py`
- Delivered families: `openai`, `anthropic`, `deepseek`, `alibaba`, `google`, `xai`, `local`.
- Delivered APIs: `load_vendor_families`, `load_vendor_family_map`, `resolve_vendor_family`.
- Guard: duplicate `model_id`, missing family, empty family, and YAML parse errors fail closed through `FamiliesError`.

### 3.2 T3.2 · allowlist loader

- PR: [#41](https://github.com/charliehzm/medharness/pull/41)
- Merge commit: `53fce6a`
- Leaf commit: `56b84bd`
- Key files: `mcp/model-router/allowlist.py`, `tests/test_model_router_allowlist.py`
- Delivered `AllowlistEntry`, `Allowlist`, `load_allowlist`, and `HotAllowlist`.
- Schema is list-based and model entries are self-contained.
- Hot reload uses mtime plus sha256; reload failure keeps the last active policy once a snapshot exists.

### 3.3 T3.3 · policy core

- PR: [#42](https://github.com/charliehzm/medharness/pull/42)
- Merge commit: `dfb49de`
- Leaf commit: `ef7ace4`
- Key files: `mcp/model-router/policy.py`, `tests/test_model_router_policy.py`
- Delivered frozen `RouteRequest` and `RouteDecision`.
- Evaluation order is marker, allowlist model id, role allowlist, data level, heterogeneity hook.
- `PolicyCore` performs no file I/O and is suitable for hot-path execution.

### 3.4 T3.4 · heterogeneity matrix

- PR: [#43](https://github.com/charliehzm/medharness/pull/43)
- Merge commit: `2ea637f`
- Leaf commit: `adde388`
- Key files: `mcp/model-router/heterogeneity.py`, `tests/test_model_router_heterogeneity.py`
- Delivered `HETEROGENEITY_RULES` and `HeterogeneityPolicy`.
- `reviewer` and `compliance` same-family routes deny.
- Missing `caller_vendor_family` denies for all roles, including docs and maintainer.

### 3.5 T3.5 · circuit breaker and rate limiter

- PR: [#44](https://github.com/charliehzm/medharness/pull/44)
- Merge commit: `069599d`
- Leaf commit: `cfd3f32`
- Key files: `mcp/model-router/limits.py`, `tests/test_model_router_limits.py`
- Delivered `CircuitBreaker`, `CircuitEvent`, and `RateLimiter`.
- Circuit key is `(agent_role, change_id)`.
- Rate key is `(agent_role, model_id)`.
- Both structures are bounded by `MAX_ACTIVE_KEYS = 1000`.

### 3.6 T3.6 · server integration

- PR: [#45](https://github.com/charliehzm/medharness/pull/45)
- Merge commit: `794a710`
- Leaf commit: `662caf5`
- Key files: `mcp/model-router/server_v2.py`, `tests/test_model_router_server_v2.py`
- Delivered `route`, `health`, and `serve --stdio`.
- Delivered `_RuntimeState`, lazy vendor-family loading, cached hot allowlists, rate limiter cache, circuit breaker, audit adapter, and token-gated `inject_allowlist`.
- Deny responses include structured `error.type`, `message`, `layer_failed`, and optional `severity`.

### 3.7 T3.7 · integration tests

- PR: [#46](https://github.com/charliehzm/medharness/pull/46)
- Merge commit: `887d232`
- Leaf commit: `484b2d9`
- Key files: `tests/test_model_router_integration.py`, `tests/fixtures/model_router_allowlists.json`
- Delivered five e2e scenarios through subprocess `route` and `serve --stdio`.
- Scenarios cover happy route, public direct deny, same-family deny, missing marker deny, and qps burst deny.
- Assertions verify audit JSONL excludes raw payload strings.

### 3.8 T3.8 · router bypass drill

- PR: [#47](https://github.com/charliehzm/medharness/pull/47)
- Merge commit: `aba1860`
- Leaf commit: `228829d`
- Key files: `tests/red-team-drills/drill_router_bypass.py`, `tests/red-team-drills/run_all.sh`
- Delivered 11 attack cases and JSON report schema.
- `run_all.sh` now runs drill 2 and fails if any expected-deny case is allowed.
- Cases are local-only and write allowlists under a temporary directory.

## 4. Architecture Decisions Referenced

T3 implements `openspec/changes/feat-edge-tier-production-v0.5.0/design.md` ADR-04.

ADR-04 decision:

- `mcp-model-router` performs runtime enforcement before routing.
- Description-level policy, hooks, and business-code self-checks were rejected because they depend on human discipline.
- Runtime denial is the single point of enforcement for model access.

ADR-04 Q1:

- Decision: allowlist schema is list-based.
- Implementation: T3.2 `AllowlistEntry` fields match each `models[]` object.
- Evidence: `tests/fixtures/model_router_allowlists.json` and T3.8 synthetic allowlists use the same schema.

ADR-04 Q2:

- Decision: circuit threshold is configurable, default `5`.
- Implementation: `CircuitBreaker(threshold=5, window_seconds=60)`.
- Evidence: T3.5 tests cover default 5 and custom threshold 3.

ADR-04 Q3:

- Decision: no inline PHI subprocess scan in router.
- Implementation: route request must include `desensitized: true`; missing or false marker denies with layer `marker`.
- Evidence: T3.3 policy test, T3.6 server test, T3.7 e2e marker scenario, T3.8 `missing-marker` case.

ADR-04 Q4:

- Decision: add `AuditAdapter` boundary and implement `FileAuditAdapter` in v0.5.
- Implementation: T3.6 writes `.audit/routing_log.jsonl`.
- T4 handoff: `ClickHouseAuditAdapter` is present as a placeholder and raises `NotImplementedError`.

## 5. Threat Model + Mitigations

| Threat class | Attack path | Mitigation | Evidence |
|---|---|---|---|
| Router bypass | Direct model id such as `gpt-4o`, `claude-opus-4.7`, or `openrouter/auto` | Active allowlist lookup must match the exact `model_id`; unknown model denies with no fallback | T3.8 cases `direct-openai-endpoint`, `direct-anthropic-endpoint`, `openrouter-bypass` |
| Self-attestation failure | Reviewer or Compliance-Agent uses same vendor family as the Coder-Agent it is reviewing | `HeterogeneityPolicy` rejects `reviewer` and `compliance` same-family routes | T3.4 unit tests, T3.6 server test, T3.8 same-family cases |
| Policy drift | Allowlist file changes, disappears, or becomes malformed while router process stays alive | `HotAllowlist` reloads by mtime+sha256; first load fails closed; reload failure preserves last active snapshot | T3.2 hot reload tests; T3.8 missing/malformed/empty-policy cases |
| Over-classification | L4 data sent to a model whose entry allows only L1-L2 or L1-L3 | `PolicyCore` compares request `data_level` against `allowed_data_levels` | T3.3 data-level test; T3.6 server test; T3.8 `l4-over-policy` |
| Missing desensitize gate | Prompt path skips T2 and sends `desensitized=false` | `PolicyCore` denies at marker layer before model selection | T3.3 marker test; T3.6 server test; T3.7 e2e; T3.8 `missing-marker` |
| Repeated probing | Same agent role repeatedly submits denied route attempts | `CircuitBreaker` opens after threshold and returns `SEV-2` | T3.5 unit tests; T3.6 five-deny server test |
| Burst abuse | Allowed model is hammered beyond policy qps | `RateLimiter` denies over-qps `(agent_role, model_id)` bucket | T3.5 unit tests; T3.6 server test; T3.7 burst scenario; T3.8 burst case |
| Audit elision | Route returns allow/deny but leaves no trail | T3.6 writes audit record on allow, policy deny, allowlist error, rate deny, invalid request, and circuit open | T3.6 audit record tests |

Residual note: T3 does not call a real LLM, so data-plane provider behavior is outside T3's direct threat model.

## 6. Test Coverage Matrix

Final T3 verification baseline:

- Full repository tests: `103 passed`.
- Red-team drill wrapper: `4` drills invoked by `tests/red-team-drills/run_all.sh`.
- Router bypass drill: `11` cases.
- Router e2e integration: `5` scenarios.
- Contract violations observed in T3 tests: `0`.

| Area | Test file or command | Coverage |
|---|---|---|
| Vendor family loader | `mcp/model-router/vendor_families.py` doctest plus PR #40 verification | unique model ids, missing keys, duplicate model id, resolve behavior |
| Allowlist loader | `tests/test_model_router_allowlist.py` | schema validation, vendor-family cross-validation, invalid data level, invalid qps, hot reload, fail-safe stale active |
| Policy core | `tests/test_model_router_policy.py` | happy path, marker deny, allowlist deny, role deny, data-level deny, no-PHI reason, heterogeneity hook, performance |
| Heterogeneity | `tests/test_model_router_heterogeneity.py` | same-family deny, cross-family allow, docs/maintainer allow, missing caller family deny, unknown role deny, PolicyCore integration |
| Limits | `tests/test_model_router_limits.py` | default threshold 5, configurable threshold, rolling expiry, isolation, qps deny, LRU bound, performance |
| Server integration | `tests/test_model_router_server_v2.py` | route, health, stdio, marker, allowlist, data-level, heterogeneity, circuit, rate, audit record structure |
| E2E router | `tests/test_model_router_integration.py` | subprocess route, stdio route, five scenarios, audit no raw payload |
| Drill 2 | `tests/red-team-drills/drill_router_bypass.py` | 11 bypass vectors and JSON report |
| Drill wrapper | `tests/red-team-drills/run_all.sh` | drill 1 recall, drill 2 router bypass, drill 3 audit replay, drill 4 injection, recall gate |

Drill status nuance:

- Drill 1 is real PHI recall with gate.
- Drill 2 is real router bypass with gate as of T3.8.
- Drill 3 (`drill_audit_replay.py`) is still a structured stub that returns pass.
- Drill 4 (`drill_injection.py`) is still a structured stub that returns pass.
- Therefore "4 drills pass" means the wrapper invokes four drill scripts successfully, not that drill 3 and drill 4 have production-grade coverage yet.

T3.8 drill 2 cases:

1. `direct-openai-endpoint`
2. `direct-anthropic-endpoint`
3. `openrouter-bypass`
4. `same-family-reviewer`
5. `same-family-compliance`
6. `l4-over-policy`
7. `missing-marker`
8. `missing-allowlist-file`
9. `malformed-allowlist`
10. `expired-allowlist`
11. `rate-limit-burst`

## 7. Audit Log Schema

T3.6 `_audit_record` currently writes 17 fields:

| Field | Meaning |
|---|---|
| `routing_log_id` | Unique route decision id generated by `uuid4().hex`. |
| `decision` | `allow` or `deny`. |
| `reason` | Auditable reason string without raw prompt text. |
| `policy_version` | Active allowlist policy version when known. |
| `duration_ms` | Rounded route gate duration. |
| `layer_failed` | `None`, `request`, `allowlist`, `marker`, `data_level`, `heterogeneity`, `rate`, or `circuit`. |
| `severity` | `None`, `WARN`, or `SEV-2`. |
| `error_type` | Structured error class name for deny path. |
| `model_id` | Requested model id from the route request. |
| `agent_role` | Caller role. |
| `data_level` | Requested data classification level. |
| `change_id` | Change-specific policy namespace. |
| `caller_vendor_family` | Caller family supplied in route metadata. |
| `desensitized` | Boolean marker proving T2 path happened before route. |
| `target_model_id` | Target model id used in the final response. |
| `vendor_family` | Target vendor family. |
| `deployment` | Target deployment string, usually `private://...` in tests. |

Audit adapter contract:

- `AuditAdapter.write_routing_decision(record: dict) -> str`
- `FileAuditAdapter` appends JSONL to `.audit/routing_log.jsonl`.
- The file adapter creates the audit directory if missing.
- The adapter returns the `routing_log_id`.

T4 placeholder:

- `ClickHouseAuditAdapter` exists in `server_v2.py`.
- It raises `NotImplementedError` in v0.5.0 edge tier.
- T4 should replace the placeholder with WORM `_audit_log` persistence, hash chaining, and ClickHouse DDL ownership.

No raw prompt contract:

- `_audit_record` does not copy arbitrary payload keys.
- Fields are derived from `RouteRequest` descriptors and selected policy metadata.
- T3.6 and T3.7 tests explicitly assert `prompt` and raw sentinel strings are absent.

## 8. Heterogeneity Policy

The current role matrix:

| `agent_role` | `same_family_allowed` | Runtime result |
|---|---:|---|
| `compliance` | `False` | Same-family target denies. Cross-family target can allow if allowlist and data level pass. |
| `reviewer` | `False` | Same-family target denies. Cross-family target can allow if allowlist and data level pass. |
| `docs` | `True` | Same-family target can allow, but `caller_vendor_family` must still be explicit. |
| `maintainer` | `True` | Same-family target can allow, but `caller_vendor_family` must still be explicit. |
| `coder` | `True` | Same-family target can allow, but `caller_vendor_family` must still be explicit. |

Fail-closed rules:

- Unknown `agent_role` denies.
- Missing, empty, or non-string `caller_vendor_family` denies.
- Target family not declared in `vendor_families.yml` denies.
- T3.4 is stricter than the minimum spec because even low-risk roles must declare caller vendor family.

Design rationale:

- The "self-attestation" failure from the v2.0 lesson is blocked by runtime, not review text.
- The matrix intentionally separates model availability from reviewer/compliance independence.
- `MODEL_ALLOWLIST.json` states who may use the model; `heterogeneity.py` states who may independently review or certify with it.

## 9. Hot Reload + Fail-safe

Hot allowlist behavior:

- `HotAllowlist.get_allowlist()` calls `_load_if_needed()`.
- `_load_if_needed()` checks file existence first.
- If the file does not exist and no snapshot exists, router fails closed.
- If the file does not exist but a snapshot exists, the last active allowlist remains active.
- If mtime and sha256 match the last snapshot, no reload work is done.
- If content changed, `load_allowlist()` performs strict validation and cross-validation.
- If reload fails after a snapshot exists, the router logs a warning and keeps the last active policy.

Circuit breaker behavior:

- Default threshold: `5`.
- Default window: `60` seconds.
- Key: `(agent_role, change_id)`.
- Storage: `OrderedDict[tuple[str, str], deque[float]]`.
- Every `record_reject` and `is_open` prunes stale timestamps by `time.monotonic()`.
- Open event returns severity `SEV-2`.
- State is in-memory only for v0.5.0.

Rate limiter behavior:

- QPS comes from `AllowlistEntry.rate_limit_qps`.
- Key: `(agent_role, model_id)`.
- Storage: `OrderedDict[tuple[str, str], deque[float]]`.
- Window: fixed 1 second.
- Limit state is bounded by `MAX_ACTIVE_KEYS = 1000`.
- State is in-memory only for v0.5.0.

Operational implication:

- Router policy can be updated per change without process restart.
- Bad policy files do not crash the router after a good policy has been loaded.
- First-load failures still deny to avoid booting into an unknown policy.

## 10. Performance Profile

Required profile:

- ADR-04 target: `< 5ms overhead per call`, excluding real LLM/provider latency.
- T3.3 pure policy loop: 10,000 evaluations average under 1ms each.
- T3.4 heterogeneity loop: 100,000 checks average under 100us each.
- T3.5 limit operations: 100,000 mixed operations under 100us per call.
- T3.6 route responses include `_meta.duration_ms`.

Local hot-path benchmark on 2026-05-23:

```json
{"iterations": 1000, "max_ms": 6.1031, "median_ms": 0.0546, "p95_ms": 0.0721, "p99_ms": 0.1423}
```

Benchmark shape:

- Temporary project root.
- One synthetic allowlist for `change-t3-perf`.
- One allowed `deepseek-v3` route.
- `rate_limit_qps=100000` to avoid rate denials during measurement.
- Hot runtime path after warmup.
- No network and no model call.

Interpretation:

- p99 route overhead is well below 5ms on the local development machine.
- One observed max outlier exceeded 5ms, likely due to file audit append / local filesystem scheduling.
- T13 packaging should re-measure inside the release image and decide whether FileAuditAdapter needs buffering before production load testing.

Verification commands used across T3:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/
bash dryrun_e2e_v2.sh --ci
bash tests/red-team-drills/run_all.sh
.venv/bin/python tests/red-team-drills/drill_router_bypass.py --out tests/red-team-drills/output/router.json
```

T3.9 verification command:

```bash
.venv/bin/ruff check .
```

## 11. Known Limitations + Follow-ups

1. `server_v2._RuntimeState.circuit_open_count()` reads `CircuitBreaker._rejects`, a private attribute.
2. Invalid-request handling records rejects and audit rows, but malformed high-volume traffic could still create a small DoS surface.
3. `RateLimiter` uses a fixed 1-second window; tests involving sleep and noisy CI may be less stable than token-bucket tests.
4. T3.7 is a useful e2e test, but it is still a mega-test with several assertions in one scenario.
5. File audit append can introduce latency outliers even when p99 stays below the router SLO.
6. `run_all.sh` executes drill 3 and drill 4, but both remain structured stubs.
7. `ClickHouseAuditAdapter` is a placeholder; T4 must implement WORM persistence and hash-chain semantics.
8. File mode and executable-bit regressions should be watched for CLI and drill scripts.
9. Allowlist `policy_version` is validated as non-empty but does not yet enforce expiration timestamps or issuer signatures.
10. `caller_vendor_family` is caller-supplied metadata; future hooks should make this harder to spoof from outside trusted agent runtimes.
11. Circuit and rate state are in-memory only; process restart clears both.
12. T3 does not run a provider call and cannot prove downstream vendor endpoint isolation.
13. Public model names remain in `vendor_families.yml` as identifiers, but routing to them is blocked unless a change allowlist explicitly permits them.
14. T3 does not solve T1's CN_NAME forward declaration.
15. T3 does not persist T2 envelope metadata into audit records; T4 owns cross-service audit joining.

Recommended follow-ups:

- T4: implement `ClickHouseAuditAdapter`.
- T4: include hash-chain / WORM evidence in route audit.
- T5: expand audit replay and injection drills so drill 3 and drill 4 stop being stubs.
- T13: re-run router latency inside the offline edge-tier image.
- T13: ensure executable bits on drill scripts and CLI entrypoints are preserved in tarball packaging.

## 12. Sign-off

Four-party sign-off status:

| Role | Sign-off | Date | Evidence |
|---|---|---|---|
| codex Coder-Agent | ✅ | 2026-05-23 | T3.1-T3.9 implementation and this audit bundle. |
| Claude Reviewer-Agent, heterogeneous | ✅ | 2026-05-23 | PRs #40-#47 reviewed before merge. |
| Compliance-Agent, heterogeneous | ✅ | 2026-05-23 | R1-R5 evidence recorded above; maintainer runs external compliance review. |
| Maintainer | ✅ | 2026-05-23 | T3.1-T3.8 merged to `main` through PRs; T3.9 pending review. |

T3 model-router runtime gate acceptance is met for v0.5.0 edge-tier scope.

T3 can hand off to T4 with:

1. Runtime route decisions.
2. File audit JSONL records.
3. A stable `AuditAdapter` boundary.
4. Error layer, severity, and policy-version fields ready for WORM persistence.

T3 can hand off to T5 with:

1. Real drill 2 router bypass implementation.
2. JSON report schema for bypass cases.
3. `run_all.sh` gate that fails when expected-deny cases are allowed.

T3 can hand off to T13 with:

1. Offline bundle requirements for `mcp/model-router`.
2. Need to preserve `vendor_families.yml`.
3. Need to package no public model credentials.
4. Need to re-measure route overhead inside the final image.
