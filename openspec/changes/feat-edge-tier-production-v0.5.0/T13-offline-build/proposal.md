# Proposal · T13 Offline Build

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task group: `T13 · build-offline.sh 离线包构建`
> Parent task list: `../tasks.md`
> Status: spec-only decomposition for maintainer review

## 1. One Sentence

T13 turns the Phase 1-3 runtime, scripts, and docs into a repeatable offline tarball that can be built on macOS or Linux and then installed on an air-gapped customer host.

## 2. Scope

In scope for T13:

- `scripts/build-offline.sh` as the main offline build driver.
- Docker build / save orchestration for the 8 MCP images already delivered in T9.
- Offline wheel capture, spaCy model bundle capture, tarball assembly, and checksum generation.
- Repeatable-build guardrails for the tarball and archive metadata.
- A final T13 audit summary and sign-off ledger.

Out of scope for T13:

- Repo-root `install.sh`, `verify.sh`, or any runtime installer logic; those remain T14/T15/T16 work.
- Full runbook content; T17 owns the real runbooks. T13 may create empty bundle directories / placeholders only.
- Any Dockerfile changes.
- Any runtime code changes in `mcp/**`.
- Any deploy-time orchestration changes in `deploy/**`.
- Any release publication workflow wiring beyond the offline build spec.

## 3. Inputs From T1-T12

T13 builds on the assets already landed:

- T1 / `mcp/phi-detector/`: Presidio + spaCy runtime image and Chinese detector dependencies.
- T2 / `mcp/desensitize/`: AES-256-GCM crypto runtime and file key provider support.
- T3 / `mcp/model-router/`: lightweight policy / allowlist runtime.
- T4 / `mcp/audit-log/`: WORM audit runtime and hashchain verification tooling.
- T8 / `.github/workflows/compliance.yml`: red-team CI / recall gate pattern.
- T9 / 8 MCP Dockerfiles + build gate tooling.
- T10 / `deploy/docker-compose.prod.yml` + `.env.production.example`: production runtime topology.
- T11 / TLS scripts and nginx 443 hardening.
- T12 / backup, restore, upgrade, teardown operational scripts.
- `VERSION`, `.dockerignore`, and the existing spec / ADR corpus.

The critical T13 inputs are the 8 MCP image names, their build contracts, and the offline bundle shape already captured in ADR-05.

## 4. Reviewer Decisions Already Accepted

- Accept D1: multi-arch strategy defaults to `linux/amd64`; `linux/arm64` is optional via explicit `--arch all` / `--arch arm64` path.
- Accept D2: image packaging uses per-image `docker save ... | gzip > images/<name>.tar.gz` artifacts.
- Accept D3: wheels are downloaded by `pip download`; cross-platform wheel policy must be explicit before implementation.
- Accept D4: `zh_core_web_sm` belongs in the offline bundle but not in runtime images.
- Accept D5: tarball naming follows `medharness-offline-v0.5.0-edge-linux-<arch>.tar.gz`.
- Accept D6: reproducibility uses `SOURCE_DATE_EPOCH` and deterministic tar options.
- Accept D7: `build-offline.sh` must run on macOS and Linux.
- Accept D8: bundle directory structure follows ADR-05 exactly; `install.sh`, `verify.sh`, and `runbooks/` are placeholders until later tasks.

## 5. Proposed T13 Shape

T13 should be split into 5 leaves:

1. shared offline build scaffolding and arch selection
2. image export / buildx integration for the 8 MCPs and supporting images
3. wheels / spaCy model capture and offline asset directories
4. tarball packaging, checksums, and reproducibility controls
5. tests, ADR-05 T13 subsection, and master ledger closeout

This keeps the high-risk artifact assembly separate from the archive-format and reproducibility review.

## 6. Why This Exists

Without T13, Phase 4 has no portable offline delivery artifact. The system would remain a set of online images and scripts instead of a deployable customer handoff package for air-gapped or tightly controlled environments.

## 7. Threat Model

| Threat | Example path | T13 mitigation target |
|---|---|---|
| Build context leakage | local secrets, `.env`, caches, or private keys accidentally enter the offline bundle | narrow copy set, explicit exclusions, checksum verification |
| Multi-arch drift | amd64 and arm64 artifacts diverge across machines or time | `SOURCE_DATE_EPOCH`, deterministic tar metadata, explicit arch selection |
| Supply-chain mismatch | wheels or images are pulled from a different version than the reviewed runtime state | pinned version inputs, explicit image export, audit summary |
| Model bundle tampering | spaCy model or offline assets are altered after build | checksum bundle and signed checksum output |
| Tarball bloat | archive exceeds customer-host transfer / disk budget | size budget gate and archive accounting |

## 8. Handoff

T13 → T14 install.sh:

- install.sh can consume the offline tarball once the package shape is frozen.
- the archive structure from ADR-05 becomes the install contract.

T13 → T15 verify.sh:

- checksum and archive validation expectations are defined by T13.

T13 → T16 signing:

- `SHA256SUMS` and archive signing hooks can be added after T13 defines the artifact set.

T13 → T19 offline e2e:

- the offline tarball becomes the fixture for no-network end-to-end install testing.

## 9. RFC Questions

- Q1: should amd64 remain the default tarball target, with arm64 optional via a flag, or should both be built by default?
- Q2: should image export remain per-image tarballs, or should the bundle also support OCI layout as an alternate archive format?
- Q3: should wheels use a fixed manylinux2014 platform constraint for cross-platform reproducibility, or auto-detect the current platform?
- Q4: should the spaCy model be always included, or guarded by an explicit include-model flag?
- Q5: should macOS require GNU tar via `gtar`, or should the script support BSD tar fallback paths?
- Q6: should `install.sh`, `verify.sh`, and companion offline scripts be copied, generated, or later symlinked from the repo root into the bundle?
- Q7: should `SOURCE_DATE_EPOCH` derive from the latest git commit timestamp, from the VERSION file, or from a fixed release timestamp?
- Q8: should `data-seed/` include only synthetic corpus plus empty schema, or additional seed assets for docs and runbooks?
