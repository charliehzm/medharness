# T10 · docker-compose.prod.yml + network isolation · leaf task plan

> Parent task group: `T10 · docker-compose.prod.yml + network isolation`
> Parent task list: `../tasks.md`
> Architecture decision target: pending maintainer ADR entry in `../design.md` after RFC answers
> Canonical spec: `../specs/T10-docker-compose.spec.md` (to be added after RFC answers if needed)
> Branch model: each leaf starts from `main` as `feat/T10.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Production deployment assets live under root `deploy/`; do not scatter compose / nginx / env templates elsewhere.
- T10 must not create or modify a development compose file.
- T10 must not modify MCP runtime code or Dockerfiles from T9.
- T10 must not generate TLS certificates or implement TLS policy; that belongs to T11.
- T10 must not implement backup / restore scripts; that belongs to T12.
- T10 must not implement offline tarball packaging; that belongs to T13.
- T10 must not publish host ports for the 8 MCP services.
- T10 must not commit real secrets, private keys, `.env` values, customer hostnames, or PHI.
- T10 should keep stubs clearly marked as placeholders until their M3-M5 production work lands.
- T10 should prefer Compose-native health and network isolation over ad hoc shell orchestration.

## Runtime Contract

The production Compose artifact must satisfy this contract:

1. Main file path is `deploy/docker-compose.prod.yml`.
2. It defines exactly two logical networks:
   - `medharness_internal` with `driver: bridge` and `internal: true`.
   - `medharness_dmz` with `driver: bridge`.
3. All 8 MCP services attach to `medharness_internal`.
4. No MCP service publishes host ports.
5. nginx is the only service attached to `medharness_dmz` and the only service that publishes a host port.
6. Image names follow `medharness/mcp-<name>:<VERSION>` or the ADR-09-approved equivalent.
7. Every service has a healthcheck, or explicitly reuses the image-level healthcheck when Compose allows that behavior.
8. `depends_on` uses `condition: service_healthy` for dependency edges selected by ADR-09.
9. Host-mounted state paths stay under `/data/medharness/*`.
10. Resource limits are present for every service:
    - `phi-detector`: 1GB memory / 1 CPU
    - `desensitize`: 512MB memory / 0.5 CPU
    - `model-router`: 512MB memory / 0.5 CPU
    - `audit-log`: 512MB memory / 0.5 CPU
    - `ci-trigger`: 256MB memory / 0.25 CPU
    - `internal-kb`: 256MB memory / 0.25 CPU
    - `pm-bridge`: 256MB memory / 0.25 CPU
    - `vector-db`: 256MB memory / 0.25 CPU
    - `nginx`: 128MB memory / 0.25 CPU
11. Restart policy is explicit for every service.
12. Compose validation must fail loud on missing services, wrong networks, host-published MCP ports, missing limits, or missing volumes.

## 6 Leaf Sub-tasks

### T10.1 · deploy scaffold + networks + volumes

- Branch: `feat/T10.1-compose-scaffold`
- Files:
  - `deploy/docker-compose.prod.yml`
  - focused test file if useful
- Scope:
  - Create `deploy/`.
  - Add the production compose shell with networks and named / host-mounted volume declarations.
  - Define version / environment placeholder strategy after ADR-09.
- Acceptance:
  - `medharness_internal` is internal-only.
  - `medharness_dmz` exists and is separate.
  - Host-mounted volume paths stay under `/data/medharness/*`.
  - No service implementation is added beyond harmless scaffold placeholders if needed.

### T10.2 · 4 production MCP services

- Branch: `feat/T10.2-production-mcp-services`
- Files:
  - `deploy/docker-compose.prod.yml`
  - focused test file if useful
- Scope:
  - Add `phi-detector`, `desensitize`, `model-router`, and `audit-log`.
  - Use T9 image names and healthcheck contracts.
  - Add production resource limits and restart policy.
  - Add dependency chain approved by ADR-09.
- Acceptance:
  - 4 production MCP services exist.
  - No production MCP service publishes a host port.
  - All production MCP services attach only to `medharness_internal`.
  - `model-router` depends on `phi-detector` and `desensitize` if ADR-09 confirms the reviewer decision.
  - `audit-log` is independently healthy and persistent.

### T10.3 · 4 stub MCP services

- Branch: `feat/T10.3-stub-mcp-services`
- Files:
  - `deploy/docker-compose.prod.yml`
  - focused test file if useful
- Scope:
  - Add `ci-trigger`, `internal-kb`, `pm-bridge`, and `vector-db`.
  - Keep services internal-only.
  - Apply stub-sized resource limits and restart policy.
  - Preserve placeholder status in comments / service metadata where Compose supports it.
- Acceptance:
  - 4 stub services exist.
  - No stub publishes a host port.
  - All stubs attach only to `medharness_internal`.
  - Stub resource limits are lower than production MCP limits.

### T10.4 · nginx DMZ entrypoint

- Branch: `feat/T10.4-nginx-dmz-entrypoint`
- Files:
  - `deploy/docker-compose.prod.yml`
  - `deploy/nginx/medharness.conf` or equivalent ADR-09-approved nginx config path
  - focused test file if useful
- Scope:
  - Add nginx as the only DMZ-facing service.
  - Attach nginx to both `medharness_dmz` and `medharness_internal`.
  - Add upstreams by service name unless ADR-09 chooses another method.
  - Leave certificate generation and TLS hardening to T11.
- Acceptance:
  - nginx is the only service with a host port.
  - nginx depends on the selected internal services via `condition: service_healthy`.
  - nginx has resource limits and restart policy.
  - No private key or real certificate is committed.

### T10.5 · compose validation tests + smoke plan

- Branch: `feat/T10.5-compose-validation`
- Files:
  - `tests/test_docker_compose_prod.py`
  - optional `deploy/README.md` if ADR-09 wants operator-facing smoke instructions here
- Scope:
  - Add static tests for service count, networks, volumes, host ports, healthchecks, resource limits, and dependency edges.
  - Add optional `docker compose config` validation if the local tool is available.
  - Define whether `docker compose up --wait` is part of CI, local smoke, or future manual verification.
- Acceptance:
  - Tests prove there are 8 MCP services plus nginx.
  - Tests prove only nginx publishes a host port.
  - Tests prove `medharness_internal` is internal-only.
  - Tests prove every service has resource limits and restart policy.
  - Tests prove expected host-mounted paths stay under `/data/medharness/*`.

### T10.6 · T10 AUDIT_BUNDLE.summary.md + 4-way sign-off

- Branch: `feat/T10.6-compose-summary`
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T10-docker-compose/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T10-docker-compose/tasks.md`
- Scope:
  - Record final T10 verification summary.
  - Update the leaf status ledger.
  - Capture R1-R5 evidence, residual risk, and T10 -> T11/T12/T13 handoff.
- Acceptance:
  - Summary includes 12 sections consistent with T7 and T9 closure docs.
  - T10.1-T10.5 PR / commit ledger is complete.
  - 4-way sign-off block is present.

## Dependency Order

```text
T10.1 -> T10.2 -> T10.4 -> T10.5 -> T10.6
      \-> T10.3 ----^
```

Rationale:

- networks and volumes must exist before services are added.
- production and stub services can be separate leaves after the scaffold.
- nginx depends on knowing the internal services it should proxy.
- validation lands after the topology exists.
- summary lands last.

## Verification Commands Per Leaf

Run the relevant subset for every leaf:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/test_docker_compose_prod.py -v
```

For static Compose validation, pending ADR-09:

```bash
docker compose -f deploy/docker-compose.prod.yml config
```

For smoke testing, pending ADR-09:

```bash
docker compose -f deploy/docker-compose.prod.yml up --wait
docker compose -f deploy/docker-compose.prod.yml ps
docker compose -f deploy/docker-compose.prod.yml down
```

For network exposure checks:

```bash
docker compose -f deploy/docker-compose.prod.yml config | grep -n "ports:"
```

For volume path checks:

```bash
docker compose -f deploy/docker-compose.prod.yml config | grep -n "/data/medharness"
```

## Open RFC Questions

Q1. Should the Compose file use an explicit version such as `3.8` / `3.9`, or omit `version` and rely on the current Compose Specification?

Q2. Should T10 include a ClickHouse container and `clickhouse_data` mount now, or keep audit-log v0.5.0 mock-only and leave real ClickHouse wiring to a later leaf?

Q3. Should nginx upstreams use Docker internal DNS service names, or fixed IPs on the internal network?

Q4. Should image tags be resolved through `${VERSION}` from root `VERSION`, a committed `.env.production.example`, or hard-coded `0.5.0-edge` defaults?

Q5. What is the minimum T10 verification level: static YAML parse, `docker compose config`, or `docker compose up --wait` smoke on a local Docker host?

Q6. Should resource limits use Compose `deploy.resources.limits`, runtime `mem_limit` / `cpus`, or both for local Compose compatibility?

Q7. How should environment variables and secrets be represented: committed `.env.production.example`, `deploy/secrets/` placeholders, host paths only, or another template format?

Q8. Should T10 publish nginx on host `443` immediately with certificate mount placeholders, or should port `443` binding wait for T11 TLS assets?
