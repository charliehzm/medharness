# T9 · 8 MCP Dockerfile · leaf task plan

> Parent task group: `T9 · 8 MCP Dockerfile`
> Parent task list: `../tasks.md`
> Architecture decision target: pending maintainer ADR entry in `../design.md` after RFC answers
> Canonical spec: `../specs/T9-mcp-dockerfile.spec.md` (to be added after RFC answers if needed)
> Branch model: each leaf starts from `main` as `feat/T9.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 substantive files.
- 3 files are allowed only when the 3rd file is wiring-only, <= 15 changed lines, and necessary.
- The 4 stub MCP Dockerfiles may be implemented in one leaf because they should be template-identical and low-risk.
- T9 must not modify MCP runtime code unless an RFC explicitly permits a tiny health shim.
- T9 must not create a Dockerfile for `mcp/prompt-injection-scan/`; it is a library, not a server.
- T9 must not modify `docker-compose.prod.yml`; orchestration belongs to T10.
- Runtime images must not install `requirements-dev.txt`.
- Docker build contexts must not copy `.env`, `.audit`, red-team output, caches, `.git`, or local virtualenv content.
- Images must run as non-root `medharness:medharness` with UID/GID `9000`.
- Every image must have a `HEALTHCHECK`, version / SPDX / maintainer labels, and an explicit workdir.
- Image scan and size checks must fail loud.

## Runtime Contract

Every MCP Dockerfile must satisfy this runtime contract:

1. Base image is `python:3.11-slim`, unless ADR-08 later approves a shared MedHarness base image.
2. Build uses at least two stages: `builder` and `runtime`.
3. Runtime stage runs as `medharness:medharness` with UID/GID `9000`.
4. Runtime stage copies only required application files and runtime dependencies.
5. Runtime stage declares labels:
   - `org.opencontainers.image.title`
   - `org.opencontainers.image.version`
   - `org.opencontainers.image.licenses=Apache-2.0`
   - `org.opencontainers.image.vendor=MedHarness`
   - `org.opencontainers.image.description`
   - `org.opencontainers.image.source`
6. Runtime stage includes a `HEALTHCHECK`.
7. Runtime command starts the MCP server or runs the existing server placeholder for stubs.
8. Image must pass:
   - build succeeds,
   - non-root smoke test proves UID is not `0`,
   - health check is present in `docker inspect`,
   - production image size `< 500MB`,
   - stub image size `< 200MB`,
   - vulnerability scanner reports `0` high or critical vulnerabilities.

Production MCP classes:

- `phi-detector`: heavy NLP image; expects Presidio / spaCy / jieba concerns.
- `desensitize`: crypto image; expects `cryptography` native wheel / OpenSSL concerns.
- `model-router`: lightweight policy image; should avoid PHI / NLP dependencies.
- `audit-log`: audit image; expects hashchain / fallback / optional ClickHouse client concerns.

Stub MCP classes:

- `ci-trigger`
- `internal-kb`
- `pm-bridge`
- `vector-db`

## 7 Leaf Sub-tasks

### T9.1 · shared Docker build contract + ignore rules

- Branch: `feat/T9.1-docker-contract`
- Files:
  - `.dockerignore`
  - optional `scripts/docker-build.sh` skeleton or docs-only checklist if ADR-08 defers script ownership
- Scope:
  - Define shared build context exclusions.
  - Capture label, user, healthcheck, and size-check expectations in one reusable pattern.
  - Prepare the path for per-MCP Dockerfiles without adding a runtime image yet if ADR-08 needs to settle first.
- Acceptance:
  - `.dockerignore` excludes local secrets, virtualenvs, caches, git metadata, audit output, red-team output, and build artifacts.
  - Shared contract is compatible with all 8 MCP directories.
  - No Dockerfile is added until the ADR-08 version / dependency decisions are answered, unless the maintainer approves.

### T9.2 · phi-detector Dockerfile

- Branch: `feat/T9.2-phi-detector-dockerfile`
- Files:
  - `mcp/phi-detector/Dockerfile`
  - focused test or build fixture file if needed
- Scope:
  - Package `mcp/phi-detector/` with Presidio, spaCy, jieba, recognizers, `fields.yml`, and `server_v3.py`.
  - Keep image size below 500MB.
  - Define a health check that exercises the server surface without using PHI.
- Acceptance:
  - `docker build` succeeds.
  - Runtime user is non-root.
  - `HEALTHCHECK` exists and is executable.
  - Smoke test uses synthetic text only.
  - Vulnerability scan has `0` high or critical findings.

### T9.3 · desensitize Dockerfile

- Branch: `feat/T9.3-desensitize-dockerfile`
- Files:
  - `mcp/desensitize/Dockerfile`
  - focused test or build fixture file if needed
- Scope:
  - Package `mcp/desensitize/` with crypto envelope, key provider, SQL metadata, and `server_v2.py`.
  - Confirm `cryptography` installs from wheels in slim runtime or compile stage.
  - Avoid copying real key material.
- Acceptance:
  - `docker build` succeeds.
  - Runtime user is non-root.
  - Health check uses synthetic input and no real PHI.
  - Image size `< 500MB`.
  - Vulnerability scan has `0` high or critical findings.

### T9.4 · model-router Dockerfile

- Branch: `feat/T9.4-model-router-dockerfile`
- Files:
  - `mcp/model-router/Dockerfile`
  - focused test or build fixture file if needed
- Scope:
  - Package `mcp/model-router/` with allowlist, policy, heterogeneity, limits, vendor family metadata, and `server_v2.py`.
  - Keep runtime dependency surface minimal.
  - Preserve R2 fail-closed routing assumptions.
- Acceptance:
  - `docker build` succeeds.
  - Runtime user is non-root.
  - Health check imports / starts the router surface without external model calls.
  - Image size `< 500MB`, with a target materially smaller than NLP images.
  - Vulnerability scan has `0` high or critical findings.

### T9.5 · audit-log Dockerfile

- Branch: `feat/T9.5-audit-log-dockerfile`
- Files:
  - `mcp/audit-log/Dockerfile`
  - focused test or build fixture file if needed
- Scope:
  - Package `mcp/audit-log/` with `server_v2.py`, hashchain, fallback writer, ClickHouse writer, and SQL schema.
  - Decide whether `clickhouse-connect` is installed now or deferred as optional runtime dependency after ADR-08.
  - Preserve WORM / audit assumptions without requiring a live ClickHouse server in smoke tests.
- Acceptance:
  - `docker build` succeeds.
  - Runtime user is non-root.
  - Health check does not require a live ClickHouse server.
  - Image size `< 500MB`.
  - Vulnerability scan has `0` high or critical findings.

### T9.6 · 4 stub MCP Dockerfiles

- Branch: `feat/T9.6-stub-mcp-dockerfiles`
- Files:
  - `mcp/ci-trigger/Dockerfile`
  - `mcp/internal-kb/Dockerfile`
  - `mcp/pm-bridge/Dockerfile`
  - `mcp/vector-db/Dockerfile`
- Scope:
  - Add template-identical minimal Dockerfiles for the 4 stub MCPs.
  - Use import-smoke health checks unless ADR-08 chooses a different stub health contract.
  - Clearly keep them as stubs; do not imply production capability.
- Acceptance:
  - All 4 stub images build.
  - All 4 run as non-root.
  - All 4 include labels and health checks.
  - Each stub image size `< 200MB`.
  - Vulnerability scan has `0` high or critical findings.

### T9.7 · docker build, size, non-root, scan gate + summary

- Branch: `feat/T9.7-docker-build-gate-summary`
- Files:
  - `scripts/docker-build.sh` or `.github/workflows/docker-build.yml` depending on ADR-08
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T9-mcp-dockerfile/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T9-mcp-dockerfile/tasks.md` (wiring/status only)
- Scope:
  - Add the final build / inspect / size / non-root / scanner gate.
  - Record final image sizes, scan results, residual risks, and handoff notes.
  - Add 4-way sign-off.
- Acceptance:
  - All 8 images build locally or in CI.
  - All 8 images pass size thresholds.
  - All 8 images pass non-root smoke checks.
  - All 8 images expose `HEALTHCHECK` metadata.
  - Vulnerability scanner reports `0` high or critical findings.
  - T9 final summary includes R1-R5 self-check and T9 -> T10/T13/T14 handoff.

## Dependency Order

```text
T9.1 -> T9.2 -> T9.7
     \-> T9.3 -> T9.7
     \-> T9.4 -> T9.7
     \-> T9.5 -> T9.7
     \-> T9.6 -> T9.7
```

## Verification Commands Per Leaf

Run the relevant subset for every leaf:

```bash
.venv/bin/ruff check .
docker build -f mcp/<name>/Dockerfile -t medharness/<name>:t9 .
docker image inspect medharness/<name>:t9
docker run --rm medharness/<name>:t9 python -c "import os; raise SystemExit(0 if os.getuid() != 0 else 1)"
```

For size checks:

```bash
docker image inspect medharness/<name>:t9 --format '{{.Size}}'
```

For healthcheck checks:

```bash
docker image inspect medharness/<name>:t9 --format '{{json .Config.Healthcheck}}'
```

For scanner checks, pending ADR-08:

```bash
trivy image --severity HIGH,CRITICAL --exit-code 1 medharness/<name>:t9
# or the ADR-approved scanner equivalent
```

For the final gate:

```bash
bash scripts/docker-build.sh --ci
```

## Open RFC Questions

Q1. Should T9 use one shared prebuilt MedHarness base image, or should each MCP Dockerfile start directly from `python:3.11-slim` for fresher base rebuilds?

Q2. What is the canonical version label source for Docker images: create a root `VERSION` file in T9.1, read `pyproject.toml` version, or pass `--build-arg VERSION` from CI?

Q3. Should runtime dependencies stay in the current global `requirements.txt`, or should T9 create per-MCP requirement slices to keep `model-router` and stub images small?

Q4. How should `HEALTHCHECK` be defined for the 4 stub MCPs that only expose placeholder `server.py`: import smoke, `--help`, or a tiny common health CLI shim?

Q5. Which vulnerability scanner is canonical for the "0 high vuln" gate: Trivy, Anchore, GitHub CodeQL / dependency review, or another maintained action?

Q6. Where should Docker build tests live: a dedicated `.github/workflows/docker-build.yml`, a reusable shell script invoked locally and by CI, or pytest subprocess tests?

Q7. How should spaCy / Presidio model assets be packaged for `phi-detector` while keeping the image under 500MB: download at build time, vendor a small model, or defer model install to T13 offline packaging?
