# T3 · model-router runtime gate · proposal

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task group: `T3 · model-router runtime gate`
> Architecture decision: `design.md` ADR-04
> Status: task-group proposal for leaf decomposition

## One-Line Goal

Turn `mcp-model-router` from a mostly allowlist / PHI-check placeholder into the runtime gate that enforces model allowlist, heterogeneous reviewer routing, data classification policy, circuit breaker, rate limiting, and fail-closed audit decisions before any model call is allowed.

## Why This Exists

MedHarness cannot rely on prompts, best-effort hooks, or developer memory to enforce model-routing compliance.

T3 makes R2 enforceable at runtime:

- The requested model must be in the active `MODEL_ALLOWLIST.json`.
- The caller `agent_role` must be allowed to route to the target `vendor_family`.
- The data classification level must be allowed for the selected model/deployment.
- Repeated rejects must trip a circuit breaker and surface SEV-2.
- Every allow / deny decision must emit an audit-ready routing record.

## In Scope

- `mcp/model-router/vendor_families.yml`
- `MODEL_ALLOWLIST.json` schema and hot-load behavior
- 3-layer route validation core
- Runtime heterogeneous check for agent role vs vendor family
- Circuit breaker and per-agent_role rate limiter
- `mcp/model-router/server_v2.py` integration
- Router bypass red-team drill implementation
- Focused and integration tests for allow, deny, bypass, over-classification, circuit, and rate paths
- Final T3 audit summary and T3 -> T4 / T5 handoff

## Out Of Scope

- Real calls to public or private LLM endpoints
- Cloud provider SDKs or credentials
- T4 ClickHouse `_audit_log` runtime implementation
- T2 desensitize implementation changes
- T1 detector changes
- Commercial billing / usage metering
- Multi-region HA router deployment

## Runtime Contract

`route_v2` must fail closed.

Allowed response:

```json
{
  "decision": "allow",
  "model_id": "qwen-max",
  "vendor_family": "alibaba",
  "deployment": "private://qwen-max",
  "routing_log_id": "<audit-id>",
  "policy_version": "T3.router.v1",
  "_meta": {"duration_ms": 0.0}
}
```

Denied response:

```json
{
  "decision": "deny",
  "reason": "model_not_in_allowlist",
  "routing_log_id": "<audit-id>",
  "severity": "WARN",
  "policy_version": "T3.router.v1",
  "_meta": {"duration_ms": 0.0}
}
```

Circuit-open response:

```json
{
  "decision": "deny",
  "reason": "circuit_open",
  "routing_log_id": "<audit-id>",
  "severity": "SEV-2",
  "policy_version": "T3.router.v1"
}
```

## 3-Layer Gate

1. **Allowlist**
   - Requested or selected model must exist in active `MODEL_ALLOWLIST.json`.
   - Missing, malformed, expired, or stale allowlist means deny.
   - No fallback to another model on deny.

2. **Heterogeneous Runtime Check**
   - Caller `agent_role` is required.
   - Target model maps to `vendor_family` through `vendor_families.yml`.
   - Policy rejects same-family reviewer / compliance routes when the task requires heterogeneity.
   - Compliance-Agent must not share vendor family with Coder-Agent for the same change review path.

3. **Data Classification**
   - Request must include data classification level, or the router derives the max level allowed by `COMPLIANCE_TAG.md`.
   - L4 / PHI-bearing prompt paths must be denied unless the prompt is already desensitized by T2.
   - If classification exceeds the selected model policy, deny.

## T2 Handoff Consumed By T3

T3 can rely on:

- `server_v2.desensitize` accepts `phi_spans + context` and returns an encrypted envelope without raw PHI in response.
- `server_v2.reverse` is token-gated with `COMPLIANCE_REVERSE_TOKEN`.
- FileKeyProvider and envelope metadata are stable for v0.5.0.
- `_phi_lookup` schema is locked, but runtime persistence is still T4.
- AES-256-GCM is the only T2 algorithm.

T3 must not assume:

- Real cloud KMS exists.
- Real ClickHouse persistence is active.
- T2 envelope metadata is a full audit event.

## Performance Target

Router policy overhead must be `< 5ms` per local policy check, excluding any future model endpoint call.

T3 tests should benchmark the pure policy path with warm loaders and synthetic requests.

## Audit Handoff

T3 must emit local audit-ready routing decision records immediately.

Until T4 lands ClickHouse WORM, this can reuse the current `.audit/routing_log.jsonl` pattern with a stable schema and a TODO handoff to T4.

Required audit fields:

- timestamp
- change_id
- agent_role
- task_type
- requested_model
- selected_model
- vendor_family
- data_classification
- decision
- reason
- severity
- policy_version
- duration_ms

The audit record must not include prompt raw text.

## Acceptance

- Allowlist miss denies.
- Same-family heterogeneity violation denies.
- Data classification over-policy denies.
- Circuit breaker opens after threshold rejects for same `agent_role`.
- Rate limiter denies bursts for same `agent_role`.
- Router bypass red-team drill has 10+ attack cases and passes.
- Pure policy overhead p99 `< 5ms`.
- All denies drop directly; no fallback model is selected.
- Every route decision produces audit-ready record.
