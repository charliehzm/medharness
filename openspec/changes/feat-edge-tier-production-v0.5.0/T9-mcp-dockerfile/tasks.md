# T9 · 8 MCP Dockerfile · leaf task plan

> Parent task group: `T9 · 8 MCP Dockerfile`
> Parent task list: `../tasks.md`
> Architecture decision target: ADR-08 already landed in `../design.md`
> Canonical spec: `../specs/T9-mcp-dockerfile.spec.md` (if needed for future amendments)
> Branch model: each leaf starts from `main` as `feat/T9.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- Every leaf PR changes <= 2 substantive files.
- 3 files are allowed only when the 3rd file is wiring-only, <= 15 changed lines, and necessary.
- The 4 stub MCP Dockerfiles may be implemented in one leaf because they are template-identical and low-risk.
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

1. Base image is `python:3.11-slim`.
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

## 8 Effective Leaf Sub-tasks

> Note: the original T9 spec described 7 leaves and bundled the build gate with the final summary. The implemented sequence split those responsibilities: T9.7 is the build gate, and T9.8 is this docs-only closure leaf.

### T9.1 · shared Docker build contract + ignore rules ✅

- Branch: `feat/T9.1-docker-contract`
- PR: [#72](https://github.com/charliehzm/medharness/pull/72)
- Merge commit: `c689d66`
- Leaf commit: `87fba3e`
- Files:
  - `.dockerignore`
  - `VERSION`
- Result: completed and merged. Build context exclusions and the canonical version source are now fixed.

### T9.2 · phi-detector Dockerfile ✅

- Branch: `feat/T9.2-phi-detector-dockerfile`
- PR: [#73](https://github.com/charliehzm/medharness/pull/73)
- Merge commit: `6bb1132`
- Leaf commit: `fb99f83`
- Files:
  - `mcp/phi-detector/Dockerfile`
  - `mcp/phi-detector/requirements.txt`
  - `tests/test_phi_detector_dockerfile.py`
- Result: completed and merged. Heavy NLP image contract is in place.

### T9.3 · desensitize Dockerfile ✅

- Branch: `feat/T9.3-desensitize-dockerfile`
- PR: [#74](https://github.com/charliehzm/medharness/pull/74)
- Merge commit: `5b94c52`
- Leaf commit: `a7eb4c2`
- Files:
  - `mcp/desensitize/Dockerfile`
  - `mcp/desensitize/requirements.txt`
  - `tests/test_desensitize_dockerfile.py`
- Result: completed and merged. Crypto image contract is in place.

### T9.4 · model-router Dockerfile ✅

- Branch: `feat/T9.4-model-router-dockerfile`
- PR: [#75](https://github.com/charliehzm/medharness/pull/75)
- Merge commit: `fa5584d`
- Leaf commit: `f29c1ad`
- Files:
  - `mcp/model-router/Dockerfile`
  - `mcp/model-router/requirements.txt`
  - `tests/test_model_router_dockerfile.py`
- Result: completed and merged. Minimal production image contract is in place.

### T9.5 · audit-log Dockerfile ✅

- Branch: `feat/T9.5-audit-log-dockerfile`
- PR: [#76](https://github.com/charliehzm/medharness/pull/76)
- Merge commit: `3ebb206`
- Leaf commit: `ccf90e9`
- Files:
  - `mcp/audit-log/Dockerfile`
  - `mcp/audit-log/requirements.txt`
  - `tests/test_audit_log_dockerfile.py`
- Result: completed and merged. Audit image contract and import-smoke health are in place.

### T9.6 · 4 stub MCP Dockerfiles ✅

- Branch: `feat/T9.6-stub-mcp-dockerfiles`
- PR: [#77](https://github.com/charliehzm/medharness/pull/77)
- Merge commit: `bed9fff`
- Leaf commit: `4d2f2bd`
- Files:
  - `mcp/ci-trigger/Dockerfile`
  - `mcp/ci-trigger/requirements.txt`
  - `mcp/internal-kb/Dockerfile`
  - `mcp/internal-kb/requirements.txt`
  - `mcp/pm-bridge/Dockerfile`
  - `mcp/pm-bridge/requirements.txt`
  - `mcp/vector-db/Dockerfile`
  - `mcp/vector-db/requirements.txt`
  - `tests/test_stub_mcp_dockerfiles.py`
- Result: completed and merged. All four stub images are template-identical and import-smoke healthy.

### T9.7 · docker build gate ✅

- Branch: `feat/T9.7-docker-build-script`
- PR: [#78](https://github.com/charliehzm/medharness/pull/78)
- Merge commit: `4e9edf4`
- Leaf commit: `6436e25`
- Files:
  - `scripts/docker-build.sh`
  - `.github/workflows/docker-build.yml`
  - `tests/test_docker_build_script.py`
- Result: completed and merged. The build helper, workflow matrix, size gate, non-root smoke, and Trivy scan are all wired.

### T9.8 · T9 AUDIT_BUNDLE.summary.md + sign-off ⏳

- Branch: `feat/T9.8-docker-summary`
- PR: pending
- Merge commit: pending
- Leaf commit: pending
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T9-mcp-dockerfile/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T9-mcp-dockerfile/tasks.md`
- Result: pending review. This leaf closes the final verification ledger and records sign-off for the full T9 build contract.

## Dependency Order

```text
T9.1 -> T9.2 -> T9.7
     \-> T9.3 -> T9.7
     \-> T9.4 -> T9.7
     \-> T9.5 -> T9.7
     \-> T9.6 -> T9.7
     \-> T9.8
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

For scanner checks:

```bash
trivy image --severity HIGH,CRITICAL --exit-code 1 medharness/<name>:t9
```

For the final build gate, run one MCP at a time or let the CI workflow fan out across all 8 MCPs:

```bash
bash scripts/docker-build.sh <mcp_name>
```

## Final Verification Snapshot

- `.venv/bin/ruff check .` -> clean.
- Final recorded repository baseline after T9.7: `301 passed, 1 skipped`.
- T9 leaf test total: `86` unit tests across T9.1-T9.7.
- `ci-trigger` build smoke: `45.7MB`.
- All 8 images are non-root by contract.
- All 8 images carry a `HEALTHCHECK`.

## 4-Way Sign-off

| Signer | Status | Notes |
|---|---|---|
| codex Coder-Agent | ✅ complete | T9.1-T9.7 are implemented and merged; T9.8 is the closure leaf. |
| Claude Reviewer-Agent (异构) | ✅ complete | Each leaf PR passed review and merge. |
| Compliance-Agent (异构) | ✅ complete | R1-R5 evidence is captured across the T9 leaves; no raw text leak path was introduced. |
| Maintainer (`charliehzm`) | ⏳ pending | This PR is the final maintainer sign-off vehicle for T9. |
