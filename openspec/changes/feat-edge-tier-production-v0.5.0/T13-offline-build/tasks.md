# T13 · Offline Build · leaf task plan

> Parent task group: `T13 · build-offline.sh`
> Parent task list: `../tasks.md`
> Canonical spec: `../specs/T13-offline-build.spec.md`
> ADR target: ADR-05 T13 subsection after RFC answers
> Branch model: each leaf starts from `main` as `feat/T13.<M>-<slug>` and opens a PR to `main`.

## Guardrails

- T13 implementation leaves must not modify MCP runtime code.
- T13 implementation leaves must not modify existing Dockerfiles unless a separate RFC explicitly reopens T9.
- T13 must reuse `scripts/docker-build.sh` behavior where reasonable and must not duplicate image-size / non-root policy without justification.
- T13 must not implement production `install.sh` or `verify.sh`; those belong to T14/T15.
- T13 must not include `.env.production`, private keys, local GPG keys, cert private keys, PHI, or local build caches in any bundle.
- T13 must support macOS and Linux build hosts.
- T13 must keep offline build artifacts under `dist/` and generated bundle subdirectories out of git.
- T13 must preserve ADR-05 directory names so T14/T15 can consume a stable tarball contract.
- T13 tests must prefer static parsing and dry-run paths unless a leaf explicitly owns a slow build path.

## Reviewer Decisions Accepted

- D1 accepted: default build is `linux/amd64`; `linux/arm64` is optional via explicit `--arch all` / `--arch arm64`.
- D2 accepted: image artifacts are independent `images/<name>.tar.gz` files created from `docker save | gzip`.
- D3 accepted: wheel download is required; exact `--platform` behavior remains RFC Q3.
- D4 accepted: `zh_core_web_sm` is bundled for offline use while runtime images keep RegexOnly defaults.
- D5 accepted: tarball names use `medharness-offline-v0.5.0-edge-linux-<arch>.tar.gz`.
- D6 accepted: reproducibility uses `SOURCE_DATE_EPOCH`, sorted tar entries, fixed owner/group, numeric owner, and stable mtimes.
- D7 accepted: macOS and Linux build hosts are first-class for T13.
- D8 accepted: ADR-05 directory structure is canonical; T13 may create placeholders for T14/T15/T17-owned files.

## Runtime Contract

The offline tarball root is:

```text
medharness-offline-v0.5.0-edge/
```

Required bundle entries:

- `VERSION`
- `BUILD_INFO`
- `install.sh` placeholder (T14 owns implementation)
- `verify.sh` placeholder (T15 owns implementation)
- `teardown.sh`
- `upgrade.sh`
- `docker-compose.yml`
- `images/`
- `wheels/`
- `models/`
- `configs/`
- `data-seed/`
- `docs-offline/`
- `runbooks/`
- `checksum/SHA256SUMS`
- `LICENSE`

Artifact contract:

- Tarball name: `medharness-offline-v0.5.0-edge-linux-<arch>.tar.gz`.
- Default architecture: `linux/amd64`.
- Optional architecture: `linux/arm64` via explicit `--arch all` or equivalent flag.
- Images are saved as per-image `*.tar.gz` files under `images/`.
- `SHA256SUMS` covers every generated file except `SHA256SUMS` and signature files.
- Reproducibility must use `SOURCE_DATE_EPOCH`, stable ownership (`0:0`), sorted file order, and stable mtimes.
- Size gate: final tarball `< 6 GB`; unpacked bundle target `< 5.5 GB`.

## 5 Leaf Sub-tasks

### T13.1 · build-offline.sh scaffold + bundle schema

Files expected:

- `scripts/build-offline.sh`
- `tests/test_build_offline_script.py`

Scope:

- Add the main script skeleton with strict mode, repo-root discovery, version parsing, arch parsing, dist path setup, and dry-run mode.
- Create the ADR-05 directory schema in dry-run / staging mode.
- Add static tests for flags, default arch, `SOURCE_DATE_EPOCH`, required directories, and "no secrets copied" guardrails.

Verification:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/test_build_offline_script.py -v
bash -n scripts/build-offline.sh
bash scripts/build-offline.sh --dry-run
```

### T13.2 · docker-build-all + image export

Files expected:

- `scripts/docker-build-all.sh`
- `tests/test_docker_build_all_script.py`

Scope:

- Add a wrapper that iterates the 8 MCP names and delegates individual builds to `scripts/docker-build.sh` where possible.
- Add `docker save | gzip` image export behavior for per-image artifacts.
- Add static tests for 8 MCP coverage, arch selection, per-image tar naming, and no registry push by default.

Verification:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/test_docker_build_all_script.py -v
bash -n scripts/docker-build-all.sh
bash scripts/docker-build-all.sh --dry-run
```

### T13.3 · wheels + model + offline asset collection

Files expected:

- `scripts/build-offline.sh`
- `tests/test_build_offline_assets.py`

Scope:

- Extend `build-offline.sh` to collect `wheels/`, `models/`, `configs/`, `data-seed/`, and placeholder `runbooks/`.
- Add `pip download` plan for per-MCP or aggregate requirements.
- Add spaCy `zh_core_web_sm` download / copy contract, subject to RFC Q4.
- Add tests for required asset directories, requirements discovery, model path, synthetic-only seed data, and exclusion of secret-bearing files.

Verification:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/test_build_offline_assets.py -v
bash -n scripts/build-offline.sh
bash scripts/build-offline.sh --dry-run --skip-docker
```

### T13.4 · tarball packaging + checksums + reproducibility

Files expected:

- `scripts/build-offline.sh`
- `tests/test_offline_tarball_contract.py`

Scope:

- Add checksum generation, deterministic tar invocation, size gate, and final tarball naming.
- Add GNU tar / BSD tar handling for macOS and Linux.
- Add tests for `SHA256SUMS`, sorted file list behavior, `SOURCE_DATE_EPOCH`, archive name, and size-budget checks.

Verification:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/test_offline_tarball_contract.py -v
bash -n scripts/build-offline.sh
bash scripts/build-offline.sh --dry-run --skip-docker
```

### T13.5 · tests + AUDIT_BUNDLE.summary + ADR-05 T13 subsection

Files expected:

- `openspec/changes/feat-edge-tier-production-v0.5.0/design.md`
- `openspec/changes/feat-edge-tier-production-v0.5.0/tasks.md`
- `openspec/changes/feat-edge-tier-production-v0.5.0/T13-offline-build/AUDIT_BUNDLE.summary.md`

Scope:

- Append ADR-05 T13 codex Q&A answers once maintainer responds.
- Update master tasks ledger for T13.
- Produce final T13 summary with R1-R5 evidence, artifact matrix, and handoff to T14/T15/T16/T19.

Verification:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/
```

## Dependency Order

```text
T13.1 scaffold
  └── T13.2 image export
        └── T13.3 wheels/models/assets
              └── T13.4 tarball/checksum/reproducibility
                    └── T13.5 summary/sign-off
```

T13.2 and T13.3 can be reviewed independently after T13.1 if both only extend dry-run / staging contracts. T13.4 must wait for both because it packages their outputs.

## Verification Commands Per Leaf

Baseline for every implementation leaf:

```bash
.venv/bin/ruff check .
bash -n scripts/build-offline.sh
```

Additional optional heavy verification:

```bash
bash scripts/build-offline.sh --arch amd64 --dry-run
bash scripts/docker-build-all.sh --dry-run
```

Final T13 verification target:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/
bash scripts/build-offline.sh --arch amd64 --dry-run
```

## Open RFC Questions

- Q1: should amd64 remain the default tarball target, with arm64 optional via a flag, or should both be built by default?
- Q2: should image export remain per-image tarballs, or should the bundle also support OCI layout as an alternate archive format?
- Q3: should wheels use a fixed manylinux2014 platform constraint for cross-platform reproducibility, or auto-detect the current platform?
- Q4: should the spaCy model be always included, or guarded by an explicit include-model flag?
- Q5: should macOS require GNU tar via `gtar`, or should the script support BSD tar fallback paths?
- Q6: should `install.sh`, `verify.sh`, and companion offline scripts be copied, generated, or later symlinked from the repo root into the bundle?
- Q7: should `SOURCE_DATE_EPOCH` derive from the latest git commit timestamp, from the VERSION file, or from a fixed release timestamp?
- Q8: should `data-seed/` include only synthetic corpus plus empty schema, or additional seed assets for docs and runbooks?
