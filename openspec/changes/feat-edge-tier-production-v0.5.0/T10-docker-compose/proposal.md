# Proposal · T10 Docker Compose Production Orchestration

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task group: `T10 · docker-compose.prod.yml + network isolation`
> Parent task list: `../tasks.md`
> Status: spec-only decomposition for maintainer review

## 1. One Sentence

T10 wires the 8 T9 MCP images into a production Docker Compose topology with internal-only MCP networking, a DMZ nginx entrypoint, host-mounted data volumes, healthcheck-based startup ordering, and bounded resource usage for a small medical SaaS deployment.

## 2. Scope

In scope for T10:

- Production Compose assets under `deploy/`.
- `deploy/docker-compose.prod.yml`.
- Two-network topology:
  - `medharness_internal`: bridge network with `internal: true`.
  - `medharness_dmz`: bridge network for the nginx edge only.
- Host-mounted data paths under `/data/medharness/*`.
- 8 MCP services using T9 image names:
  - `medharness/mcp-phi-detector:<VERSION>`
  - `medharness/mcp-desensitize:<VERSION>`
  - `medharness/mcp-model-router:<VERSION>`
  - `medharness/mcp-audit-log:<VERSION>`
  - `medharness/mcp-ci-trigger:<VERSION>`
  - `medharness/mcp-internal-kb:<VERSION>`
  - `medharness/mcp-pm-bridge:<VERSION>`
  - `medharness/mcp-vector-db:<VERSION>`
- Resource limits suitable for a single-host 30-person company deployment.
- Compose validation tests and a smoke-test plan.
- Final T10 audit summary and 4-way sign-off.

Out of scope for T10:

- Development compose files.
- Kubernetes / Helm / Swarm.
- TLS certificate generation, renewal warnings, HSTS policy, and BYO certificate installer support; those belong to T11.
- Backup / restore scripts; those belong to T12.
- Offline tarball assembly; that belongs to T13.
- Image registry push and digest-pinning automation; that belongs to T14.
- Rewriting MCP runtime servers.
- CI/CD trigger implementation for the `ci-trigger` stub.

## 3. Inputs From T9

T10 depends directly on T9 outputs:

- 8 Docker images exist with the `medharness/mcp-<name>:<VERSION>` naming convention.
- Every image runs as non-root UID/GID `9000`.
- Every image has a Docker `HEALTHCHECK`.
- Every image carries OCI labels including version, source, vendor, and Apache-2.0 license.
- T9 split per-MCP runtime dependencies so Compose does not need to install Python packages.
- T9 root `VERSION` is the canonical image version source.
- `scripts/docker-build.sh` and `.github/workflows/docker-build.yml` provide the build / size / Trivy gate.

T9 healthcheck types that T10 should reuse:

| MCP | Image | Healthcheck type |
|---|---|---|
| `phi-detector` | `medharness/mcp-phi-detector:<VERSION>` | real endpoint, `server_v3.py health` |
| `desensitize` | `medharness/mcp-desensitize:<VERSION>` | real endpoint, `server_v2.py health` |
| `model-router` | `medharness/mcp-model-router:<VERSION>` | real endpoint, `server_v2.py health` |
| `audit-log` | `medharness/mcp-audit-log:<VERSION>` | import smoke in v0.5.0 |
| `ci-trigger` | `medharness/mcp-ci-trigger:<VERSION>` | import smoke |
| `internal-kb` | `medharness/mcp-internal-kb:<VERSION>` | import smoke |
| `pm-bridge` | `medharness/mcp-pm-bridge:<VERSION>` | import smoke |
| `vector-db` | `medharness/mcp-vector-db:<VERSION>` | import smoke |

## 4. Reviewer Decisions Already Accepted

I accept all 6 reviewer decisions as T10 guardrails:

1. Directory structure: `deploy/` at the repository root owns production deployment assets.
2. Networks: `medharness_internal` is internal-only; `medharness_dmz` is the nginx edge network.
3. Volumes: host-mounted `/data/medharness/*` paths are the default because customers need physical control over data.
4. Resource limits: per-service memory and CPU limits target one host with about 4GB memory and 4 CPU total budget.
5. Healthcheck chain: `depends_on` should use `condition: service_healthy` where the Compose implementation supports it.
6. Service exposure: the 8 MCP services publish no host ports; only nginx publishes to the host.

Qualifications to settle in ADR-09:

- Compose resource-limit syntax differs between local Docker Compose and Swarm-oriented `deploy.resources`; T10 should pick one canonical representation.
- `clickhouse_data` is named as an optional host mount, but audit-log remains v0.5.0 mock-only after T9.5.
- nginx belongs in T10 as the DMZ entrypoint, while TLS certificate generation and TLS hardening belong to T11.

## 5. Proposed T10 Shape

T10 should be split into 6 leaves:

1. T10.1 shared scaffold: create `deploy/`, production compose base, networks, and host volume declarations.
2. T10.2 production MCP services: add `phi-detector`, `desensitize`, `model-router`, and `audit-log`.
3. T10.3 stub MCP services: add `ci-trigger`, `internal-kb`, `pm-bridge`, and `vector-db` with explicit stub labels / comments.
4. T10.4 nginx DMZ entrypoint: add nginx service and minimal reverse-proxy wiring that can receive TLS assets from T11.
5. T10.5 compose validation tests and smoke plan: parse YAML, assert services / networks / volumes / limits, and optionally run `docker compose config`.
6. T10.6 final summary and sign-off: add T10 audit bundle summary and update the T10 task ledger.

This keeps the high-risk topology pieces separate:

- networks and volumes are reviewed before services depend on them,
- production MCP services are reviewed apart from stubs,
- nginx exposure is reviewed independently from internal services,
- validation tests land before final sign-off.

## 6. Why This Exists

T9 created images; T10 makes them deployable as a single-host production topology.

Without T10:

- MCP containers can be built but not started as a coherent system.
- Customers have no documented internal / DMZ network boundary.
- Healthchecks exist but are not used for startup ordering.
- Host-mounted audit and keystore paths remain undefined.
- Resource usage can drift beyond the target small-company deployment budget.
- T13 offline packaging would not have a production compose artifact to include.

T10 turns image artifacts into a controlled deployment surface.

## 7. Threat Model

| Threat | Example path | T10 mitigation target |
|---|---|---|
| Network exposure | MCP services accidentally publish host ports | Only nginx publishes to host; all MCPs attach to internal network only |
| DMZ attack surface | nginx can reach too many containers or leak internal ports | nginx attaches to DMZ and internal; MCPs do not attach to DMZ |
| Volume path traversal | mis-mounted host paths expose unexpected directories | fixed `/data/medharness/*` mount points and narrow per-service mounts |
| Keystore leakage | desensitize key material has loose permissions | keystore mount is isolated and later leaves enforce file mode expectations |
| Audit tampering | audit data is not persisted across restart | audit-log receives persistent host mount under `/data/medharness/audit` |
| depends_on race | nginx starts before services are healthy | `condition: service_healthy` dependency chain |
| Resource exhaustion | phi-detector or a stub consumes host memory / CPU | per-service CPU / memory caps |
| Stub overclaim | placeholder services look production-complete | stub services remain internal-only and documented as placeholders |

## 8. Handoff

T10 -> T11 TLS:

- T10 owns the nginx service and DMZ network placement.
- T11 should provide certificate generation, BYO certificate wiring, TLS policy, and expiry checks.
- T10 should leave clear certificate mount points or placeholders without generating secrets.

T10 -> T12 backup:

- T10 defines the host volume paths that T12 must back up.
- T12 can target `audit_log_data`, `keystore_data`, and optional stateful service data.
- T10 should not implement backup scripts or retention policy.

T10 -> T13 offline tarball:

- T13 can copy `deploy/` into the offline package configs.
- T13 can substitute image loading / local tags while preserving the service topology.
- T10 should keep environment templates free of real secrets so offline packaging remains safe.

## 9. RFC Questions

The following questions need maintainer answers before T10.1 starts. They are duplicated in `tasks.md` for tracking.

Q1. Should the Compose file use an explicit version such as `3.8` / `3.9`, or omit `version` and rely on the current Compose Specification?

Q2. Should T10 include a ClickHouse container and `clickhouse_data` mount now, or keep audit-log v0.5.0 mock-only and leave real ClickHouse wiring to a later leaf?

Q3. Should nginx upstreams use Docker internal DNS service names, or fixed IPs on the internal network?

Q4. Should image tags be resolved through `${VERSION}` from root `VERSION`, a committed `.env.production.example`, or hard-coded `0.5.0-edge` defaults?

Q5. What is the minimum T10 verification level: static YAML parse, `docker compose config`, or `docker compose up --wait` smoke on a local Docker host?

Q6. Should resource limits use Compose `deploy.resources.limits`, runtime `mem_limit` / `cpus`, or both for local Compose compatibility?

Q7. How should environment variables and secrets be represented: committed `.env.production.example`, `deploy/secrets/` placeholders, host paths only, or another template format?

Q8. Should T10 publish nginx on host `443` immediately with certificate mount placeholders, or should port `443` binding wait for T11 TLS assets?
