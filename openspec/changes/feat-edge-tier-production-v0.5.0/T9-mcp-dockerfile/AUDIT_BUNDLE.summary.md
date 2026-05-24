# T9 · 8 MCP Dockerfile · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T9 · 8 MCP Dockerfile`
> Status: final verification recorded for T9 scope; T9.8 is the docs-only closure leaf
> Date: 2026-05-24
> Scope: final verification summary only; no runtime code in T9.8

## 1. Change Overview

T9 delivered a complete containerization contract for all 8 MCP surfaces: four production images, four stub images, a shared build contract, per-image size and non-root enforcement, and CI-visible scan gates.

T9 was specified as 7 leaves in the original task decomposition, but the implementation path split the final build gate from the final summary. In practice, T9.7 implemented the build gate, and T9.8 closes the documentation ledger. So the delivered T9 implementation has 8 effective leaves when the closing docs leaf is counted.

| Leaf | PR | Merge commit | Leaf commit | One-line result |
|---|---:|---|---|---|
| T9.1 | [#72](https://github.com/charliehzm/medharness/pull/72) | `c689d66` | `87fba3e` | Added the shared Docker build contract via `.dockerignore` and root `VERSION`. |
| T9.2 | [#73](https://github.com/charliehzm/medharness/pull/73) | `6bb1132` | `fb99f83` | Added the heavy `phi-detector` multi-stage Dockerfile with Presidio / spaCy / jieba slice. |
| T9.3 | [#74](https://github.com/charliehzm/medharness/pull/74) | `5b94c52` | `a7eb4c2` | Added the `desensitize` Dockerfile with crypto envelope, key provider, and SQL metadata. |
| T9.4 | [#75](https://github.com/charliehzm/medharness/pull/75) | `fa5584d` | `f29c1ad` | Added the minimal production `model-router` Dockerfile with stdlib-first packaging. |
| T9.5 | [#76](https://github.com/charliehzm/medharness/pull/76) | `3ebb206` | `ccf90e9` | Added the `audit-log` Dockerfile with import-smoke health and v0.5.0 mock-only runtime behavior. |
| T9.6 | [#77](https://github.com/charliehzm/medharness/pull/77) | `bed9fff` | `4d2f2bd` | Added four stub MCP Dockerfiles with import-smoke health checks and comment-only requirements. |
| T9.7 | [#78](https://github.com/charliehzm/medharness/pull/78) | `4e9edf4` | `6436e25` | Added `scripts/docker-build.sh`, `.github/workflows/docker-build.yml`, and the build-gate test. |
| T9.8 | pending | pending | pending | Records the final T9 verification summary, residual risks, and 4-way sign-off; this is the docs-only closure leaf. |

## 2. Compliance Posture

| Redline | Result | Evidence |
|---|---|---|
| R1 PHI never enters raw prompts | YES | T9.2-T9.6 Dockerfiles and T9.7 build script carry only metadata and build references; no PHI payloads are introduced. |
| R2 models route by allowlist | N/A for T9 runtime surface | T9 does not touch router policy logic. |
| R3 full audit record | YES for build / scan evidence | T9.7 writes JSON build reports and CI SARIF artifacts for every MCP image. |
| R4 test data compliance | YES | T9 tests are static contract checks or build smoke checks; no production samples or fixtures were introduced. |
| R5 license permanence | YES | T9 Dockerfiles carry Apache-2.0 OCI labels and do not alter repository licensing. |

R1 details:

- T9 Dockerfiles only copy the files each image needs.
- No leaf writes raw text payloads into logs or build output.
- The stub images explicitly stay as placeholder servers.

R3 details:

- T9.7 emits per-image JSON reports under `/tmp/medharness-build`.
- The workflow uploads SARIF for Trivy scans.
- The final build gate fails loud on size or non-root regressions.

## 3. Implementation Summary

### 3.1 T9.1 · shared Docker build contract + ignore rules

- PR: [#72](https://github.com/charliehzm/medharness/pull/72)
- Merge commit: `c689d66`
- Leaf commit: `87fba3e`
- Files:
  - `.dockerignore`
  - `VERSION`
- Result: completed and merged. The build context excludes secrets, caches, VCS metadata, artifacts, and local virtualenv noise; `VERSION` anchors the image version source.

### 3.2 T9.2 · phi-detector Dockerfile

- PR: [#73](https://github.com/charliehzm/medharness/pull/73)
- Merge commit: `6bb1132`
- Leaf commit: `fb99f83`
- Files:
  - `mcp/phi-detector/Dockerfile`
  - `mcp/phi-detector/requirements.txt`
  - `tests/test_phi_detector_dockerfile.py`
- Result: completed and merged. The heavy NLP image uses a multi-stage slim base, a non-root runtime, a health check on `server_v3.py health`, and a per-MCP dependency slice.

### 3.3 T9.3 · desensitize Dockerfile

- PR: [#74](https://github.com/charliehzm/medharness/pull/74)
- Merge commit: `5b94c52`
- Leaf commit: `a7eb4c2`
- Files:
  - `mcp/desensitize/Dockerfile`
  - `mcp/desensitize/requirements.txt`
  - `tests/test_desensitize_dockerfile.py`
- Result: completed and merged. The crypto image keeps the runtime narrow, avoids key material, and preserves a non-root health-checked deployment surface.

### 3.4 T9.4 · model-router Dockerfile

- PR: [#75](https://github.com/charliehzm/medharness/pull/75)
- Merge commit: `fa5584d`
- Leaf commit: `f29c1ad`
- Files:
  - `mcp/model-router/Dockerfile`
  - `mcp/model-router/requirements.txt`
  - `tests/test_model_router_dockerfile.py`
- Result: completed and merged. The smallest production MCP image keeps dependency surface minimal while still validating routing-related runtime files.

### 3.5 T9.5 · audit-log Dockerfile

- PR: [#76](https://github.com/charliehzm/medharness/pull/76)
- Merge commit: `3ebb206`
- Leaf commit: `ccf90e9`
- Files:
  - `mcp/audit-log/Dockerfile`
  - `mcp/audit-log/requirements.txt`
  - `tests/test_audit_log_dockerfile.py`
- Result: completed and merged. The audit-log image uses import-smoke health because `server_v2.py` has no CLI main in v0.5.0.

### 3.6 T9.6 · 4 stub MCP Dockerfiles

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
- Result: completed and merged. The four placeholder images are template-identical, non-root, and import-smoke healthy.

### 3.7 T9.7 · docker build gate

- PR: [#78](https://github.com/charliehzm/medharness/pull/78)
- Merge commit: `4e9edf4`
- Leaf commit: `6436e25`
- Files:
  - `scripts/docker-build.sh`
  - `.github/workflows/docker-build.yml`
  - `tests/test_docker_build_script.py`
- Result: completed and merged. The helper script builds one image at a time, checks size, verifies non-root UID 9000, and emits JSON; the workflow matrix builds all 8 images and runs Trivy HIGH/CRITICAL scans.

### 3.8 T9.8 · T9 AUDIT_BUNDLE.summary.md + sign-off

- PR: pending
- Merge commit: pending
- Leaf commit: pending
- Files:
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T9-mcp-dockerfile/AUDIT_BUNDLE.summary.md`
  - `openspec/changes/feat-edge-tier-production-v0.5.0/T9-mcp-dockerfile/tasks.md`
- Result: pending review. This leaf closes the final verification ledger and records sign-off for the full T9 build contract.

## 4. ADR-08 Alignment

T9 matches `openspec/changes/feat-edge-tier-production-v0.5.0/design.md` ADR-08:

| ADR-08 decision | T9 implementation | Evidence |
|---|---|---|
| Each image starts from `python:3.11-slim` | yes | T9.2-T9.6 all use slim Python as the base. |
| Canonical version source is root `VERSION` | yes | T9.1 creates `VERSION`; T9.7 strips newline and passes it as a build arg. |
| Per-MCP dependency slices | yes | T9.2-T9.6 each carry their own `requirements.txt`. |
| Stub health contract is import smoke | yes | T9.6 uses `python -c "import server"` for all 4 stub images. |
| Trivy is the scanner | yes | T9.7 workflow uses `aquasec/trivy-action` with HIGH/CRITICAL severity. |
| Build script + CI workflow split | yes | `scripts/docker-build.sh` and `.github/workflows/docker-build.yml` are both present. |
| spaCy / Presidio model packaging deferred | yes | T9.2 keeps the runtime slice small; heavier offline model work remains deferred to T13. |

Q1-Q7 closure:

- Q1: answered as direct `python:3.11-slim` per image.
- Q2: answered with a root `VERSION` file.
- Q3: answered with per-MCP requirement slices plus global union in the repo.
- Q4: answered with import-smoke health for stubs.
- Q5: answered with Trivy `HIGH,CRITICAL`.
- Q6: answered with `scripts/docker-build.sh` plus `.github/workflows/docker-build.yml`.
- Q7: answered by keeping the heavy spaCy model path out of v0.5.0 and deferring the richer offline asset story.

## 5. Threat Model + Mitigations

| Threat class | Attack path | Mitigation | Evidence |
|---|---|---|---|
| Secret leakage into build context | `.env`, caches, `.git`, red-team outputs, or local venv copied into images | `.dockerignore` excludes these paths | T9.1 |
| PHI leakage into image metadata | image labels or build output mention sensitive payloads | Dockerfiles and build script only carry versioning and provenance metadata | T9.2-T9.7 |
| Root escalation | runtime container runs as UID 0 | every Dockerfile switches to `medharness:medharness` UID/GID 9000 | T9.2-T9.6 |
| Oversized images | runtime drifts past the edge-tier budget | size gates in `scripts/docker-build.sh` and per-image thresholds | T9.7 |
| Vulnerable packages | high / critical CVEs ship unnoticed | Trivy HIGH/CRITICAL scan gate in CI | T9.7 |
| Placeholder stub overreach | stub images look production-ready | stub labels explicitly mark them as v0.5.0-edge placeholders | T9.6 |
| Healthcheck drift | a server image ships without a live readiness signal | every image has a healthcheck, with import-smoke fallback where needed | T9.2-T9.6 |

## 6. Test Coverage Matrix

Final recorded baseline:

- Full repository tests: `301 passed, 1 skipped`.
- T9 leaf test total: `86` unit tests across T9.1-T9.7.
- Build smoke baseline: `ci-trigger` image built successfully at about `45.7MB`.

| Leaf | Test file or command | Count | Coverage |
|---|---|---:|---|
| T9.1 | docs / config only | 0 | build contract and ignore rules |
| T9.2 | `tests/test_phi_detector_dockerfile.py` | 9 | heavy image contract and per-MCP dependency slice |
| T9.3 | `tests/test_desensitize_dockerfile.py` | 10 | crypto image contract and key-exclusion checks |
| T9.4 | `tests/test_model_router_dockerfile.py` | 11 | stdlib-first production image and routing runtime files |
| T9.5 | `tests/test_audit_log_dockerfile.py` | 12 | import-smoke health, v0.5.0 mock-only runtime, SQL copy contract |
| T9.6 | `tests/test_stub_mcp_dockerfiles.py` | 33 | four stub images, empty requirements, import-smoke health |
| T9.7 | `tests/test_docker_build_script.py` | 11 | build script, workflow matrix, Trivy wiring, report output |
| T9.8 | docs only | 0 | summary and sign-off only |

## 7. Per-MCP Image Inventory

| MCP | Image name | Size target | Verified / estimated size | Healthcheck type |
|---|---|---:|---:|---|
| phi-detector | `medharness/mcp-phi-detector:VERSION` | `< 500MB` | estimate only in T9.8 | real endpoint (`server_v3.py health`) |
| desensitize | `medharness/mcp-desensitize:VERSION` | `< 500MB` | estimate only in T9.8 | real endpoint (`server_v2.py health`) |
| model-router | `medharness/mcp-model-router:VERSION` | `< 500MB` | estimate only in T9.8 | real endpoint (`server_v2.py health`) |
| audit-log | `medharness/mcp-audit-log:VERSION` | `< 500MB` | estimate only in T9.8 | import smoke |
| ci-trigger | `medharness/mcp-ci-trigger:VERSION` | `< 200MB` | measured `45.7MB` | import smoke |
| internal-kb | `medharness/mcp-internal-kb:VERSION` | `< 200MB` | estimate only in T9.8 | import smoke |
| pm-bridge | `medharness/mcp-pm-bridge:VERSION` | `< 200MB` | estimate only in T9.8 | import smoke |
| vector-db | `medharness/mcp-vector-db:VERSION` | `< 200MB` | estimate only in T9.8 | import smoke |

## 8. Build + Scan Pipeline

T9.7 closes the operational loop for image builds.

- `scripts/docker-build.sh` builds one MCP image at a time.
- The script reads `VERSION`, passes `VERSION` and `GIT_COMMIT` as build args, checks image size, and verifies a non-root UID of `9000`.
- The script writes a JSON report for downstream automation.
- `.github/workflows/docker-build.yml` matrix-builds all 8 MCP images.
- CI uses `aquasec/trivy-action` with `HIGH,CRITICAL` severity and an exit code of `1`.
- Workflow artifacts retain build reports and SARIF output.
- The build workflow cron is offset one hour after the compliance workflow so the two jobs do not collide.

## 9. Non-root + HEALTHCHECK Matrix

| MCP | Non-root UID | HEALTHCHECK implementation |
|---|---:|---|
| phi-detector | 9000 | `python server_v3.py health` |
| desensitize | 9000 | `python server_v2.py health` |
| model-router | 9000 | `python server_v2.py health` |
| audit-log | 9000 | `python -c "from server_v2 import AuditLogServerV2"` |
| ci-trigger | 9000 | `python -c "import server"` |
| internal-kb | 9000 | `python -c "import server"` |
| pm-bridge | 9000 | `python -c "import server"` |
| vector-db | 9000 | `python -c "import server"` |

All 8 images are non-root by construction. The two healthcheck styles are intentional:

- real endpoint for images with CLI health commands
- import-smoke fallback where the runtime surface is only a class or stub module

## 10. Known Limitations + Follow-ups

1. `desensitize` still has inter-file coupling between `server_v2.py` and `server.py` substitutions; that runtime shape was not refactored in T9.
2. `model-router` still depends on `pyyaml` for `vendor_families.yml` parsing, so its runtime is not literally stdlib-only.
3. `audit-log` `server_v2.py` has no CLI `main`, so health is import-smoke rather than a direct endpoint call.
4. `audit-log` uses a sleep-loop entrypoint as a v0.5.0 compromise; a CLI-based entrypoint should replace it once the class surface grows a real main.
5. `clickhouse-connect` remains mock-only in T9.5 and belongs in a later integration leaf.
6. `phi-detector` remains the heaviest image and still deserves a real measured size table from the CI workflow, not just the single smoke build.
7. T9.7 records a real build smoke only for `ci-trigger`; the other 7 images are enforced by the workflow contract but not manually built in this closure leaf.
8. SBOM generation, registry push, and multi-arch `buildx` are still future work, not T9 scope.
9. `scripts/docker-build.sh` assumes `VERSION` is a simple single-line value; the newline strip is deliberate and should remain guarded.
10. macOS development hosts do not support the Linux WORM semantics from T4.6, but T9 is not affected because the container build path itself is platform-agnostic.

## 11. Handoff Notes

T9 -> T10 docker-compose:

- T10 can reference the final image names `medharness/mcp-<name>:VERSION`.
- Service startup can rely on container health status rather than probing ad hoc ports.
- The non-root UID/GID 9000 convention should be preserved for mounted volumes.

T9 -> T13 offline build:

- `scripts/docker-build.sh` gives a reproducible image contract for offline packaging.
- Per-MCP requirement slices are now explicit and can be vendored per image.
- The heavier NLP / crypto dependencies can be curated as offline wheels later.

T9 -> T14 image registry push:

- `scripts/docker-build.sh` already supports `--push`.
- Registry credentials, digest pinning, and SBOM publication remain future work.
- The CI workflow already captures the artifacts needed to wire those follow-ups in later.

## 12. 4-Way Sign-off

| Signer | Status | Notes |
|---|---|---|
| codex Coder-Agent | ✅ complete | T9.1-T9.7 are implemented and merged; T9.8 is the docs-only closure leaf. |
| Claude Reviewer-Agent (异构) | ✅ complete | Each leaf PR passed review and merge. |
| Compliance-Agent (异构) | ✅ complete | R1-R5 evidence is captured across the T9 leaves; no raw text leak path was introduced. |
| Maintainer (`charliehzm`) | ⏳ pending | This PR is the final maintainer sign-off vehicle for T9. |
