# Changelog

> 遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) + [SemVer 2.0](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- **§D.1 合规脊柱（hook-order spine）**: every model call transits `phi-detector → desensitize → model-router → prompt-injection-scan → base relay → outbound-safety`, welded into the new-api fork as a single gate middleware (`vendor/new-api/middleware/medharness_compliance.go`). Invariants: deny-silent (generic 503 · 0 upstream connection), base-no-autonomy, fallback-in-`allowed_model_set`, cache-after-gate, audit 双写. Proven end-to-end by `scripts/int5b_relay_smoke.sh`.
- **B1 zero-trust tier**: the gate middleware is the ONLY signer of the tier signature (HMAC-SHA256) and `mcp/model-router` the ONLY verifier — clients can no longer self-assert `data_level`. `MODEL_ROUTER_TIER_SECRET` must be identical on new-api + model-router and is never sent to clients.
- **A0 Console BFF** (`mcp/a0-api/`, BE-5/6/6b): read-only aggregation — `GET /api/v1/{posture,traffic,events,cost,channels,upstreams}`, audit lineage, config snapshots, audit-export write, config-propose approval queue, and an admin read-only proxy (`/api/v1/admin/{users,tokens,channels}`, B5 whitelist serializers). 0-PHI output guard + ClickHouse fail-closed.
- **BE-9 outbound-safety**: post-call ⑥ hook welded in; async-NLP path with an inline catch for missed detections.
- **outbound-safety + prompt-injection-scan containerized**: single-stage slim images, non-root UID 9000, stdlib-only, healthchecked — now first-class services in the prod compose and the CI build/scan matrix (11 images total).
- **Self-host deploy**: `deploy/docker-compose.prod.yml` hardened for §D.1 (gate services run `serve --http`, full `depends_on` health-gating, tier-secret wiring, per-change `MODEL_ALLOWLIST` volume) + `deploy/.env.production.example`; `scripts/{gen-tls,setup-worm}.sh`.
- **Integration smokes** (synthetic data · 0-PHI · no real provider): `scripts/int5b_relay_smoke.sh` (relay E2E — ALLOW→200 to mock upstream, DENY→generic 503 + 0 upstream connections) and `scripts/int5_console_smoke.sh` (Console-live — real ClickHouse + real A0).

### Changed

- BE-8 egress allowlist (DMZ): nginx exposes ONLY `/v1/*` (gated relay) + `/api/v1/*` (A0 Console) + `/health`; bare `/api/route` hard-denied behind a default-deny catch-all; the MCP control plane (model-router / audit-log) stays internal-only and is never proxied at the edge.
- ClickHouse 24 compat: `_audit_log` / `phi_lookup` TTL wrapped in `toDateTime(...)`; DateTime64 JSONEachRow inserts use space-separated `YYYY-MM-DD HH:MM:SS.fff`.

### Security

- Client-supplied `data_level` is no longer trusted (B1); heterogeneity routing denies on an empty caller vendor family.
- Deny path proven to open **zero** upstream connections (INT-5b relay E2E).

### Documented

- `docs/deploy/README.md` — self-host quickstart for the §D.1 stack.
- `docs/integration/INT-6-console-live-e2e.md` — Console live-mode E2E runbook + 0-PHI live renders.

### Known Limitations

- Real LLM provider channels are operator-configured in new-api admin.
- `ci-trigger` / `internal-kb` / `pm-bridge` / `vector-db` are intentional v0.5.0-edge placeholders.
- Real OIDC / multi-tenant / billing are post-v1.0.

## [0.1.0-alpha] - 2026-05-__

### Added · 首发

- 6 层架构骨架：L1 模型 / L2 Harness / L3 Skill / L4 SOP / L5 合规 / L6 治理
- **23 Skill** SKILL.md（合规 5 / 通用 16 / micro 别名 2）
- **6 Sub-agent**：PM / Coder / Reviewer / Compliance / Memory-Curator / Data-Steward
- **8 MCP server** v2 实现（占位 + 本地 demo）：
  - phi-detector / desensitize / model-router / audit-log
  - internal-kb / vector-db / ci-trigger / pm-bridge
- **9 Hook 脚本** warn 默认（block 可配）
- **12+5 步双通道 SOP** 全文
- **AUDIT_BUNDLE schema** + snapshot_packer 实现
- **31 fields.yml**（中文医疗字段，Presidio 兼容）
- **9 培训文档** + 90 天督导方法论
- 完整示例 change `示例-患者匹配最小可行版/` 可端到端跑通
- `dryrun_e2e_v2.sh` 自动 install + 自动跑通 Step 0-12
- `tools/customize.py` 交互式向导

### Documented

- README 5 分钟上手路径
- CONTRIBUTING.md 含合规自检 5 问
- SECURITY.md PHI 泄漏 / 审计绕过披露通道
- 6 层架构文档
- 12 步 SOP 文档
- 与开源生态依赖关系（Presidio / OpenSpec / Spec-Kit / Anthropic Skills / MCP）

### Known Limitations

- 公共 LLM API 阶段（M1-M5）依赖 `phi-desensitize` 前置
- Hook 技术上可绕过；社区版用 warn 默认
- Presidio 中文医疗 recognizer 召回率约 92-96%
