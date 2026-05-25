# T10 · docker-compose.prod orchestration · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T10 · docker-compose.prod.yml + network isolation`
> Status: final verification recorded for T10 scope; T10.2 is the docs + validation closure leaf
> Date: 2026-05-25
> Scope: final verification summary only; no deployment runtime code in T10.2

## 1. Change Overview

T10 turned the 8 T9 MCP images into one production Compose topology with internal-only MCP networking, a DMZ nginx entrypoint, host-mounted data paths, healthcheck-driven ordering, and per-service resource limits.

T10 was specified as 2 leaves in the revised decomposition. T10.1 implemented the entire topology, and T10.2 closes the validation and audit ledger.

| Leaf | PR | Merge commit | Leaf commit | One-line result |
|---|---:|---|---|---|
| T10.1 | [#82](https://github.com/charliehzm/medharness/pull/82) | `8e2ba6d` | `b010721` | Added `deploy/docker-compose.prod.yml`, `deploy/nginx/medharness.conf`, and the committed env template. |
| T10.2 | pending | pending | pending | Adds static compose contract tests plus the final audit summary and sign-off. |

## 2. Compliance Posture

| Redline | Result | Evidence |
|---|---|---|
| R1 PHI never enters raw prompts | YES | The compose file, nginx config, and env template only contain deployment metadata, image names, and `/data/medharness/*` paths. |
| R2 models route by allowlist | N/A for T10 runtime surface | T10 wires deployment topology only; routing policy remains in T3 / T9 runtime surfaces. |
| R3 full audit record | YES | T10.2 adds the final validation tests and records the compose topology ledger for the deployment surface. |
| R4 test data compliance | YES | T10 tests are static YAML / text contract checks with no live customer data, fixtures, or production samples. |
| R5 license permanence | YES | T10 does not touch license files and uses public nginx image metadata only. |

R1 details:

- `deploy/docker-compose.prod.yml` contains service names, resource limits, healthchecks, and host path mounts only.
- `deploy/.env.production.example` contains only `VERSION=0.5.0-edge`.
- No secrets, hostnames, keys, or PHI are committed.

R3 details:

- `deploy/docker-compose.prod.yml` encodes the production service graph and dependency ordering.
- `tests/test_docker_compose_prod.py` freezes the contract with static assertions.
- The audit summary closes the deployment ledger and handoff notes.

## 3. Implementation Summary

### 3.1 T10.1 · production compose topology + nginx DMZ config

- PR: [#82](https://github.com/charliehzm/medharness/pull/82)
- Merge commit: `8e2ba6d`
- Leaf commit: `b010721`
- Files:
  - `deploy/docker-compose.prod.yml`
  - `deploy/nginx/medharness.conf`
  - `deploy/.env.production.example`
- Result: completed and merged. The production topology now contains 8 MCP services, one nginx edge service, two logical networks, host-mounted audit and keystore paths, and resource limits for every service.

### 3.2 T10.2 · compose validation + AUDIT_BUNDLE.summary.md + sign-off

- PR: pending
- Merge commit: pending
- Leaf commit: pending
- Files:
  - `tests/test_docker_compose_prod.py`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T10-docker-compose/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T10-docker-compose/tasks.md`
- Result: pending review. This leaf freezes the Compose contract in tests and records the final verification ledger for T10.

## 4. ADR-09 Alignment

T10 matches `openspec/changes/feat-edge-tier-production-v0.5.0/design.md` ADR-09:

| ADR-09 decision | T10 implementation | Evidence |
|---|---|---|
| Compose uses current spec defaults | yes | Top-level `version` is omitted. |
| ClickHouse remains mock-only | yes | No ClickHouse service or `clickhouse_data` mount is introduced. |
| nginx upstreams use internal DNS | yes | `deploy/nginx/medharness.conf` points to `model-router` and `audit-log` service names. |
| Image tags come from `.env.production.example` | yes | `deploy/.env.production.example` provides `VERSION=0.5.0-edge`. |
| Verification level is static parse + `docker compose config` | yes | T10.2 tests parse YAML, and local validation ran `docker compose config`. |
| Resource limits use `deploy.resources.limits` | yes | Every service has Compose deploy limits. |
| Env / secret template is committed, real env is ignored | yes | Template is committed; the real `.env.production` remains excluded. |
| nginx exposes 80 now, 443 later | yes | 80 is published; 443 is left as a comment for T11. |

Q1-Q8 closure:

- Q1: answered by omitting `version`.
- Q2: answered by keeping ClickHouse mock-only.
- Q3: answered with internal DNS service names.
- Q4: answered with `${VERSION}` from `.env.production.example`.
- Q5: answered with static YAML parse plus `docker compose config`.
- Q6: answered with `deploy.resources.limits`.
- Q7: answered with committed env template plus real env exclusion.
- Q8: answered with 80 open and 443 deferred to T11.

## 5. Threat Model + Mitigations

| Threat class | Attack path | Mitigation | Evidence |
|---|---|---|---|
| Network exposure | MCP services accidentally publish host ports | Only nginx has `ports:` in Compose | T10.1 + T10.2 |
| DMZ attack surface | nginx becomes a general-purpose ingress to all services | nginx only depends on `model-router` and `audit-log`, and it stays on DMZ + internal only | T10.1 |
| Volume path traversal | host mounts escape the intended state directory | only `/data/medharness/audit` and `/data/medharness/keystore` are used | T10.1 |
| depends_on race | edge traffic starts before internal dependencies are healthy | `service_healthy` dependency edges are explicit | T10.1 + T10.2 |
| Resource exhaustion | one service crowds out the host | per-service memory / CPU caps are asserted in tests | T10.1 + T10.2 |
| Secrets leak | real env values or private keys get committed | template only, no secret values | T10.1 |
| False deployment confidence | compose file drifts from the intended contract | static tests pin service count, networks, ports, limits, and dependencies | T10.2 |

## 6. Test Coverage Matrix

Final recorded T10 validation set:

- New T10 leaf tests: `17`.
- Full repository tests after T10.2: `318 passed, 1 skipped`.
- T10 specific tests: `17 passed`.

| Check | Mechanism | Coverage |
|---|---|---|
| Compose syntax | `yaml.safe_load` | file parses as structured YAML |
| Service count | static assertion | 9 services total |
| Port exposure | static assertion | only nginx publishes ports |
| Networks | static assertion | `medharness_internal` and `medharness_dmz` only |
| Resource limits | static assertion | every service has CPU and memory limits |
| Startup ordering | static assertion | `model-router` and nginx dependency edges |
| Host mounts | static assertion | audit and keystore remain under `/data/medharness/*` |
| Image tag contract | static assertion | services use `${VERSION}` |
| Nginx config | text assertion | upstream blocks exist for `model_router` and `audit_log` |
| Env template | text assertion | `VERSION=0.5.0-edge` is present |

## 7. Service Topology

| Service | Image | Network(s) | Volume(s) | Depends on | Resource limit |
|---|---|---|---|---|---|
| phi-detector | `medharness/mcp-phi-detector:${VERSION}` | internal | none | none | 1GB / 1 cpu |
| desensitize | `medharness/mcp-desensitize:${VERSION}` | internal | `/data/medharness/keystore` | none | 512MB / 0.5 cpu |
| model-router | `medharness/mcp-model-router:${VERSION}` | internal | none | phi-detector, desensitize | 512MB / 0.5 cpu |
| audit-log | `medharness/mcp-audit-log:${VERSION}` | internal | `/data/medharness/audit` | none | 512MB / 0.5 cpu |
| ci-trigger | `medharness/mcp-ci-trigger:${VERSION}` | internal | none | none | 256MB / 0.25 cpu |
| internal-kb | `medharness/mcp-internal-kb:${VERSION}` | internal | none | none | 256MB / 0.25 cpu |
| pm-bridge | `medharness/mcp-pm-bridge:${VERSION}` | internal | none | none | 256MB / 0.25 cpu |
| vector-db | `medharness/mcp-vector-db:${VERSION}` | internal | none | none | 256MB / 0.25 cpu |
| nginx | `nginx:1.27-alpine` | dmz + internal | `deploy/nginx/medharness.conf` | model-router, audit-log | 128MB / 0.25 cpu |

## 8. Network + Volume Map

- `medharness_internal`
  - `driver: bridge`
  - `internal: true`
  - attaches all 8 MCP services and nginx
- `medharness_dmz`
  - `driver: bridge`
  - attaches nginx only
- Audit volume
  - host path: `/data/medharness/audit`
  - container path: `/data/medharness/audit`
- Keystore volume
  - host path: `/data/medharness/keystore`
  - container path: `/data/medharness/keystore`

The topology keeps all MCP services off the host network except the nginx DMZ entrypoint.

## 9. Healthcheck Chain

- `phi-detector` uses its image-level `server_v3.py health` command.
- `desensitize` and `model-router` use their image-level `server_v2.py health` commands.
- `audit-log` remains import-smoke healthy because v0.5.0 has no CLI main.
- The four stub MCP services remain import-smoke healthy.
- `model-router` waits on `phi-detector` and `desensitize`.
- `nginx` waits on `model-router` and `audit-log`.
- `audit-log` stays independent because its state machine self-manages startup.

## 10. Known Limitations + Follow-ups

1. T11 enables `443:443` and certificate mounts.
2. T11 updates `deploy/nginx/medharness.conf` with a TLS server block and 80 -> 443 redirect.
3. T12 owns backup strategy for audit, keystore, and certificate material.
4. ClickHouse remains v0.6+ work and must align with `audit-log` `clickhouse-connect` packaging.
5. nginx proxies only `model-router` and `audit-log`; the other six MCPs remain internal stdio surfaces by design.
6. The four stub MCP services start as placeholders and still have no production business behavior.
7. Resource limits are static; future deployments may tune swap, `oom_score_adj`, or host-specific quotas.
8. Full runtime `docker compose up --wait` verification remains a later environment-level smoke, not a T10 acceptance requirement.
9. CI and local validation prove the topology contract, but they do not create real customer data or secrets.
10. T10.2 intentionally stops at validation and sign-off; backup, TLS hardening, and offline packaging remain separate leaves.

## 11. Handoff Notes

T10 -> T11 TLS:

- enable `443:443` in `deploy/docker-compose.prod.yml`
- add the TLS server block to `deploy/nginx/medharness.conf`
- add cert path environment variables to the production env template

T10 -> T12 backup:

- back up `/data/medharness/audit`
- back up `/data/medharness/keystore`
- preserve the nginx config and env template as deployment artifacts

T10 -> T13 offline tarball:

- include `deploy/docker-compose.prod.yml`
- include `deploy/nginx/medharness.conf`
- include `deploy/.env.production.example`

## 12. 4-Way Sign-off

| Signer | Status | Notes |
|---|---|---|
| codex Coder-Agent | ✅ complete | T10.1 implemented the topology; T10.2 closes validation and summary. |
| Claude Reviewer-Agent (异构) | ✅ complete | T10 leaf structure was reviewed and the compose contract was tightened to 2 leaves. |
| Compliance-Agent (异构) | ✅ complete | R1-R5 evidence is captured in the compose tests and this summary. |
| Maintainer (`charliehzm`) | ⏳ pending | This PR is the final maintainer sign-off vehicle for T10. |
