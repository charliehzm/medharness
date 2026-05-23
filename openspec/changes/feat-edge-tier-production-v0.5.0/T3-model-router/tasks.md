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

### T3.1 · vendor_families.yml schema + loader ✅

- Branch: `feat/T3.1-vendor-families-loader`
- PR: [#40](https://github.com/charliehzm/medharness/pull/40)
- Merge commit: `378807c`
- Leaf commit: `f2b7ee2`
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
- Result: completed and merged. Vendor-family map and strict loader are locked for router use.

### T3.2 · MODEL_ALLOWLIST.json schema + hot loader ✅

- Branch: `feat/T3.2-allowlist-hot-loader`
- PR: [#41](https://github.com/charliehzm/medharness/pull/41)
- Merge commit: `53fce6a`
- Leaf commit: `56b84bd`
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
- Result: completed and merged. List-based allowlist, cross-validation, and fail-safe hot reload are live.

### T3.3 · 3-layer validation core ✅

- Branch: `feat/T3.3-policy-core`
- PR: [#42](https://github.com/charliehzm/medharness/pull/42)
- Merge commit: `dfb49de`
- Leaf commit: `ef7ace4`
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
- Result: completed and merged. Pure policy core now enforces marker, allowlist, role, data-level, and heterogeneity hook order.

### T3.4 · heterogeneous runtime matrix ✅

- Branch: `feat/T3.4-heterogeneity-matrix`
- PR: [#43](https://github.com/charliehzm/medharness/pull/43)
- Merge commit: `2ea637f`
- Leaf commit: `adde388`
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
- Result: completed and merged. Heterogeneity runtime matrix is active and fail-closed on missing caller family.

### T3.5 · circuit breaker + rate limiter ✅

- Branch: `feat/T3.5-circuit-rate-limit`
- PR: [#44](https://github.com/charliehzm/medharness/pull/44)
- Merge commit: `069599d`
- Leaf commit: `cfd3f32`
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
- Result: completed and merged. Circuit breaker and rate limiter are bounded, in-memory, and production-wired.

### T3.6 · server_v2 integration ✅

- Branch: `feat/T3.6-server-v2-runtime-gate`
- PR: [#45](https://github.com/charliehzm/medharness/pull/45)
- Merge commit: `794a710`
- Leaf commit: `662caf5`
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
- Result: completed and merged. Router runtime is now wired through loaders, policy core, heterogeneity, limits, and audit adapter.

### T3.7 · router integration tests ✅

- Branch: `feat/T3.7-router-integration-tests`
- PR: [#46](https://github.com/charliehzm/medharness/pull/46)
- Merge commit: `887d232`
- Leaf commit: `484b2d9`
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
- Result: completed and merged. E2E subprocess coverage proves route and stdio gates behave coherently on synthetic allowlists.

### T3.8 · drill 2 router bypass implementation ✅

- Branch: `feat/T3.8-router-bypass-drill`
- PR: [#47](https://github.com/charliehzm/medharness/pull/47)
- Merge commit: `aba1860`
- Leaf commit: `228829d`
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
- Result: completed and merged. Drill 2 is real, gated, and exercised by `run_all.sh`.

### T3.9 · T3 final verification and audit summary ✅

- Branch: `feat/T3.9-model-router-verify`
- PR: pending
- Merge commit: pending
- Leaf commit: pending
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
- Result: completed. Final verification bundle and sign-off are frozen in markdown only.

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

## T3 完成签字

提案人 · charliehzm · 2026-05-23 ✅

Compliance Officer · charliehzm（兼任）· 2026-05-23 ✅

Tech Lead · charliehzm · 2026-05-23 ✅

Reviewer-Agent · Claude Code · 2026-05-23 ✅

T3 model-router runtime gate · acceptance 100% met · 已可作为 T4 audit-log 的路由审计入口 + T5 drill 2 的 router bypass 基线
