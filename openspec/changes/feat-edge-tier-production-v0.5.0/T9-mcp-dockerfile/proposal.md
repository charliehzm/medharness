# Proposal · T9 MCP Dockerfiles

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task group: `T9 · 8 MCP Dockerfile`
> Parent task list: `../tasks.md`
> Status: spec-only decomposition for maintainer review

## 1. One Sentence

T9 packages the 8 MCP servers as non-root, multi-stage Python 3.11 Docker images with health checks, labels, size checks, and vulnerability scanning gates.

## 2. Scope

In scope for T9:

- 8 Dockerfiles under the existing MCP server directories:
  - `mcp/phi-detector/`
  - `mcp/desensitize/`
  - `mcp/model-router/`
  - `mcp/audit-log/`
  - `mcp/ci-trigger/`
  - `mcp/internal-kb/`
  - `mcp/pm-bridge/`
  - `mcp/vector-db/`
- A shared Dockerfile pattern: `python:3.11-slim`, builder/runtime stages, non-root runtime user, labels, and health checks.
- Image build / size / non-root smoke-test tooling.
- Vulnerability scan wiring for "0 high vuln" acceptance.
- A final T9 audit summary and 4-way sign-off.

Out of scope for T9:

- `docker-compose.prod.yml`, networks, volumes, or orchestration; that belongs to T10.
- Image registry push / provenance publishing; that belongs to T14 unless explicitly pulled forward.
- Offline tarball packaging; that belongs to T13, though T9 should leave clean handoff notes.
- Runtime rewrites of MCP servers.
- Dockerfile for `mcp/prompt-injection-scan/`; it is a detector library, not an MCP server.
- Production ClickHouse, KMS, RAG, vector DB, or model endpoint integration.

## 3. Inputs From T1-T8

T9 builds on the runtime modules already landed:

- T1 / `mcp/phi-detector/`: production-grade detector path with `server_v3.py`, recognizers, `fields.yml`, Presidio, spaCy, and Chinese NLP dependencies.
- T2 / `mcp/desensitize/`: production-grade desensitize path with `server_v2.py`, `key_provider/`, `crypto_envelope.py`, `cryptography`, and SQL metadata.
- T3 / `mcp/model-router/`: production-grade routing path with `server_v2.py`, allowlist / policy modules, vendor family metadata, and mostly stdlib runtime behavior.
- T4 / `mcp/audit-log/`: production-grade audit path with `server_v2.py`, hashchain, fallback writer, ClickHouse writer, and SQL schema.
- T7 / `mcp/prompt-injection-scan/`: detector library only; no Dockerfile in T9.
- T8 / `.github/workflows/compliance.yml`: red-team CI now exists, but Docker build / scan should be a separate T9 verification path.

The 4 stub MCPs are intentionally lower scope for v0.5.0:

- `mcp/ci-trigger/`
- `mcp/internal-kb/`
- `mcp/pm-bridge/`
- `mcp/vector-db/`

Dependency pressure observed from current runtime files:

- `requirements.txt` is global and includes heavy packages such as Presidio, spaCy, `faker`, `cryptography`, `zstandard`, `httpx`, and `jieba`.
- `requirements-dev.txt` is for test / lint / docs and should not be copied into runtime images unless a leaf proves it is needed.
- `pyproject.toml` declares package version `0.1.0a0`; there is no root `VERSION` file today.

## 4. Reviewer Decisions Already Accepted

- Accept: use `python:3.11-slim` as the uniform base image because the parent spec names it and CI already targets Python 3.11.
- Accept: use multi-stage Dockerfiles with a builder stage for wheels / build deps and a slim runtime stage.
- Accept: use a non-root `medharness:medharness` runtime user with UID/GID `9000`.
- Accept: every Dockerfile must include a `HEALTHCHECK`; production MCPs should prefer runtime health behavior, while stubs can use import smoke checks if no endpoint exists.
- Accept: every Dockerfile must include version, SBOM / SPDX, and maintainer labels.
- Accept: image size and non-root checks belong in a build / smoke script plus CI-friendly commands; production images target `< 500MB`, stubs target `< 200MB`.

Potential qualifications to resolve through RFC:

- A root `VERSION` file does not exist yet, so label version source needs an ADR-08 answer.
- `docker scan` is no longer the only common scanner path; Trivy / Anchore / GitHub CodeQL each imply different CI behavior.
- Per-MCP dependency slices may be necessary to keep images small; blindly installing the global `requirements.txt` will overweight `model-router` and the stubs.

## 5. Proposed T9 Shape

T9 should be split into 7 leaves:

1. shared Docker build contract and scaffolding
2. `phi-detector` Dockerfile
3. `desensitize` Dockerfile
4. `model-router` Dockerfile
5. `audit-log` Dockerfile
6. 4 stub MCP Dockerfiles
7. build / size / non-root / vulnerability scan tooling and final sign-off

This keeps the four production images reviewable and lets the heavy `phi-detector` dependency problem stand alone.

## 6. Why This Exists

Phase 3 starts moving from local scripts to deployable services. Without T9:

- the 8 MCP servers cannot be run consistently in production containers,
- root containers can widen the blast radius of a compromised MCP process,
- dependency bloat can hide supply-chain exposure and push images beyond edge deployment constraints,
- health checks cannot be wired into T10 Compose,
- and T13 offline packaging lacks a concrete image build target.

T9 turns the runtime modules into container artifacts that can be inspected, scanned, and smoke-tested before orchestration work begins.

## 7. Threat Model

| Threat | Example path | T9 mitigation target |
|---|---|---|
| Image vulnerability | A base image or dependency has high CVEs | pinned base family, vulnerability scan gate, narrow runtime deps |
| Root escalation | MCP process runs as root and writes host-mounted paths | non-root `medharness` user, owned workdir, no privileged runtime assumption |
| Supply-chain drift | Docker build pulls unintended dev or transitive dependencies | builder/runtime split, dependency slices, lock / scan follow-up |
| Secret leakage | Build context copies local env, caches, or audit output | `.dockerignore`, narrow `COPY`, no `.env` or output artifacts |
| Health blind spot | Compose sees a dead process as healthy | explicit `HEALTHCHECK` per image |
| Bloated edge images | Global deps make every MCP large | per-MCP dependency policy and size checks |
| Stub overclaim | Placeholder MCP images look production-complete | stub health checks remain import-smoke only and are documented as stubs |

## 8. Handoff

T9 -> T10 docker-compose:

- T10 can reference the 8 image names, non-root runtime users, and health checks from T9.
- T10 should wire service dependencies around Docker `HEALTHCHECK` status instead of inventing new liveness probes.

T9 -> T13 offline build:

- T13 can package the Docker build context, wheels, and images into an offline tarball.
- Dependency-slice decisions from ADR-08 should feed directly into offline wheel curation.

T9 -> T14 image registry push:

- T14 can add registry push, tags, digest pinning, and SBOM / provenance publication after T9 build artifacts exist.
- T9 should leave image names and labels predictable enough for T14 automation.

## 9. RFC Questions

The following questions need maintainer answers before T9.1 starts. They are duplicated in `tasks.md` for tracking.

Q1. Should T9 use one shared prebuilt MedHarness base image, or should each MCP Dockerfile start directly from `python:3.11-slim` for fresher base rebuilds?

Q2. What is the canonical version label source for Docker images: create a root `VERSION` file in T9.1, read `pyproject.toml` version, or pass `--build-arg VERSION` from CI?

Q3. Should runtime dependencies stay in the current global `requirements.txt`, or should T9 create per-MCP requirement slices to keep `model-router` and stub images small?

Q4. How should `HEALTHCHECK` be defined for the 4 stub MCPs that only expose placeholder `server.py`: import smoke, `--help`, or a tiny common health CLI shim?

Q5. Which vulnerability scanner is canonical for the "0 high vuln" gate: Trivy, Anchore, GitHub CodeQL / dependency review, or another maintained action?

Q6. Where should Docker build tests live: a dedicated `.github/workflows/docker-build.yml`, a reusable shell script invoked locally and by CI, or pytest subprocess tests?

Q7. How should spaCy / Presidio model assets be packaged for `phi-detector` while keeping the image under 500MB: download at build time, vendor a small model, or defer model install to T13 offline packaging?
