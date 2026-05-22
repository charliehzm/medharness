# T3 · model-router runtime gate · leaf task plan

> Parent task group: `T3 · model-router runtime gate`
> Parent task list: `../tasks.md`
> Architecture decision: `../design.md` ADR-04
> Branch model: each leaf starts from `main` as `feat/T3.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 substantive files.
- 3 files are allowed only when the 3rd file is wiring-only, <= 15 changed lines, and necessary.
- 4+ files must be split.
- T3 must not add direct public LLM calls.
- T3 must not log prompt raw text.
- T3 must fail closed: deny, never fallback, when policy inputs are missing or invalid.
- T3 must preserve T2 R1 handoff: model prompts are expected to be desensitized before route.
- T3 must keep audit-ready records even before T4 ClickHouse WORM lands.
- T3 is not complete until router bypass drill 2 is real and passes.

## Runtime Policy Contract

T3 enforces ADR-04:

1. Model in active `MODEL_ALLOWLIST.json`.
2. Caller `agent_role` and target `vendor_family` satisfy heterogeneous runtime policy.
3. Data classification level is allowed by target model/deployment policy.

Failure mode is always `drop`:

- Deny response.
- No fallback model.
- Audit-ready routing record.
- Circuit breaker can escalate repeated rejects for one `agent_role` to `SEV-2`.

## Leaf Sub-tasks

### T3.1 · vendor_families.yml schema + loader

- Branch: `feat/T3.1-vendor-families-loader`
- Files:
  - `mcp/model-router/vendor_families.yml`
  - `mcp/model-router/vendor_families.py`
- Scope:
  - Define vendor family mapping for OpenAI, Anthropic, DeepSeek, Alibaba/Qwen, Google/Gemini, xAI, and local/private.
  - Implement strict loader with duplicate-model detection and actionable errors.
  - Provide `resolve_vendor_family(model_id) -> str`.
  - Keep matching deterministic and offline.
- Acceptance:
  - Loader resolves known models from ADR-04 examples.
  - Unknown model fails closed.
  - Duplicate model across families fails.
  - No network, no LLM calls.

### T3.2 · MODEL_ALLOWLIST.json schema + hot loader

- Branch: `feat/T3.2-allowlist-hot-loader`
- Files:
  - `mcp/model-router/allowlist.py`
  - `tests/test_model_router_allowlist.py`
- Scope:
  - Implement strict allowlist schema validation and hot reload by file mtime / content hash.
  - Support model entries with task_type, model_id, vendor_family override optional, deployment, max_data_level, and heterogeneity tags.
  - Validate `issued_by`, `valid_until`, and schema version.
  - Missing / malformed / expired allowlist fails closed.
- Acceptance:
  - Happy path loads.
  - Missing required key denies.
  - Expired allowlist denies.
  - Hot reload observes file update without process restart.
  - No prompt text logged.

### T3.3 · 3-layer validation core

- Branch: `feat/T3.3-policy-core`
- Files:
  - `mcp/model-router/policy.py`
  - `tests/test_model_router_policy.py`
- Scope:
  - Implement allowlist, vendor_family, and data classification gate as pure functions.
  - Return structured `RouteDecision`.
  - Enforce drop/no-fallback on deny.
  - Measure local policy duration.
- Acceptance:
  - Allowlist miss -> deny.
  - Unknown vendor_family -> deny.
  - Data level over max -> deny.
  - L4 prompt without desensitized marker / T2 envelope reference -> deny.
  - p99 pure policy overhead < 5ms on synthetic benchmark.

### T3.4 · heterogeneous runtime matrix

- Branch: `feat/T3.4-heterogeneity-matrix`
- Files:
  - `mcp/model-router/heterogeneity.py`
  - `tests/test_model_router_heterogeneity.py`
- Scope:
  - Implement `agent_role x vendor_family` heterogeneity checks.
  - Encode Coder-Agent, Reviewer-Agent, Compliance-Agent, Docs-Agent, and Maintainer roles.
  - Reject Compliance-Agent / Reviewer-Agent same-family checks when policy requires heterogeneity.
  - Include runtime check for "Compliance-Agent 与 Coder 同模型/同 vendor_family" violation.
- Acceptance:
  - Coder OpenAI -> Compliance OpenAI denies.
  - Coder OpenAI -> Compliance Anthropic allows.
  - Docs low-risk route can allow same family when policy says not required.
  - Missing agent_role fails closed.

### T3.5 · circuit breaker + rate limiter

- Branch: `feat/T3.5-circuit-rate-limit`
- Files:
  - `mcp/model-router/limits.py`
  - `tests/test_model_router_limits.py`
- Scope:
  - Add in-memory per-agent_role reject counter with rolling window.
  - Add in-memory per-agent_role token bucket or fixed-window rate limiter.
  - Circuit opens after configurable reject threshold and returns `SEV-2`.
  - Keep state bounded and testable.
- Acceptance:
  - N rejects for same agent_role opens circuit.
  - Circuit state is isolated by change_id + agent_role.
  - Rate burst over threshold denies.
  - Allowed requests consume limiter without opening circuit.
  - No persistent secrets or prompt text stored.

### T3.6 · server_v2 integration

- Branch: `feat/T3.6-server-v2-runtime-gate`
- Files:
  - `mcp/model-router/server_v2.py`
  - `tests/test_model_router_server_v2.py`
- Scope:
  - Wire T3 loaders and policy core into `route_v2`.
  - Preserve CLI and stdio compatibility.
  - Emit audit-ready routing records without prompt raw text.
  - Keep `inject_allowlist` token-gated or explicitly fail closed if token missing.
- Acceptance:
  - `health`, `route`, and stdio smoke pass.
  - Allow response includes model_id, vendor_family, endpoint/deployment, routing_log_id, policy_version.
  - Deny response includes reason, routing_log_id, policy_version, severity.
  - Prompt raw text is not written into `.audit/routing_log.jsonl`.
  - Deny does not fallback to another model.

### T3.7 · router integration tests

- Branch: `feat/T3.7-router-integration-tests`
- Files:
  - `tests/test_model_router_integration.py`
  - `tests/fixtures/model_router_allowlists.json`
- Scope:
  - Add synthetic integration coverage for bypass / over-classification / heterogeneity / rate limiting.
  - Use temp change directories and tmp `.audit`.
  - Fixture contains no real credentials or endpoints.
- Acceptance:
  - Allow happy path.
  - Public direct model not in allowlist denies.
  - Same-family reviewer/compliance route denies.
  - L4 without T2 desensitized marker denies.
  - Burst rate limit denies.
  - Fixture is synthetic and does not require fingerprint CLI unless JSONL is introduced.

### T3.8 · drill 2 router bypass implementation

- Branch: `feat/T3.8-router-bypass-drill`
- Files:
  - `tests/red-team-drills/drill_router_bypass.py`
  - `tests/red-team-drills/run_all.sh`
- Scope:
  - Replace stub drill 2 with real router bypass cases.
  - Include 10+ attack cases:
    - direct public OpenAI endpoint
    - direct Anthropic endpoint
    - OpenRouter endpoint
    - same-family reviewer route
    - compliance-agent same-family route
    - L4 over-policy route
    - missing allowlist
    - malformed allowlist
    - expired allowlist
    - rate-limit burst
  - Report pass/fail, case ids, and reasons.
- Acceptance:
  - All expected denies are denied.
  - Drill emits JSON report.
  - `run_all.sh` fails if drill 2 fails.
  - No actual public API calls are made.

### T3.9 · T3 final verification and audit summary

- Branch: `feat/T3.9-model-router-verify`
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T3-model-router/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T3-model-router/tasks.md`
- Scope:
  - Record final T3 verification numbers after T3.1-T3.8 are merged.
  - Mark leaf tasks complete with PRs, commits, commands, and residual risks.
  - Include R1-R5 self-check and T3 -> T4/T5 handoff.
- Acceptance:
  - Summary includes allowlist, heterogeneity, data-level, circuit, limiter, drill 2, dryrun, and red-team status.
  - `tasks.md` has completion sign-off block.
  - No code changes.

## Dependency Order

```text
T3.1 -> T3.2 -> T3.3 -> T3.6 -> T3.7 -> T3.8 -> T3.9
                  \-> T3.4 -> T3.6
                  \-> T3.5 -> T3.6
```

## Verification Commands Per Leaf

Run the relevant subset for every leaf:

```bash
ruff check .
ruff format .
pytest tests/
bash dryrun_e2e_v2.sh --ci
```

For T3 leaves that touch router runtime behavior, also run:

```bash
pytest tests/test_model_router*.py -q
bash tests/red-team-drills/run_all.sh
```

For T3.8 and later, also verify:

```bash
python tests/red-team-drills/drill_router_bypass.py
```

## Open Review Questions

1. Should T3.2 allowlist schema be list-based (`models: [...]`) or task_type map-based for backward compatibility with current `server_v2.py`?
2. What exact reject threshold should open circuit breaker in v0.5.0 edge tier: 3, 5, or configurable default 5?
3. Should T3.6 keep phi-detector subprocess check from current `server_v2.py`, or rely on T1/T2 upstream desensitize marker and leave raw-PHI gate to hooks?
4. Should audit-ready routing records stay in `.audit/routing_log.jsonl` until T4, or should T3.6 add an adapter interface for future T4 wiring?
