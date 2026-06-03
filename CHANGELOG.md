# Changelog

> 遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) + [SemVer 2.0](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.0.0] - 2026-06-04

> 社区版首个稳定发布。在 §D.1 合规脊柱 + A0 Console BFF 之上补齐用户体系、出站
> 幻觉启发式、配额/成本诚实面与 4 个轻量 MCP 的真实实现；对外商业门面文案收口。

### Added

- **用户管理（完整）**: A0 用户管理写代理 `POST /api/v1/admin/users[/{id}/{update,password,status,role,delete}]`（经 new-api 管理令牌、走 `medharness_internal` 内网），登录签发会话 token（HMAC-SHA256 JWS）→ Console 持久会话（刷新不掉登录）；角色层级守卫（只能操作严格更低角色）；管理序列化器展示员工身份（用户名/邮箱）而患者 PHI 仍 0（运行时 `assert_no_patient_phi` + e2e DOM 双护栏）。
- **A1 出站幻觉启发式**: `mcp/outbound-safety` 分类器在 有害拦截 + PHI 回流 之上新增医疗幻觉规则（虚假安全 / 武断确诊 / 擅自改量 / 伪造权威——告警，不阻断）；A0 出站 gate 据此诚实翻 built。
- **A4 4 个轻量 MCP 做实**: internal-kb（TF-IDF 检索）/ vector-db（内存哈希向量化 + 余弦）/ ci-trigger（flags + 审计落盘）/ pm-bridge（工单存储 + JSONL 审计）——均为单机 stdlib 真实实现，不再是占位。

### Changed

- **A2 配额/限流诚实面**: 底座配额强制（预扣 + 结算）作为已建 gate 上屏；RPM 限流标注「可配置」；posture「用量与成本护栏」翻 built。
- **A3 实时成本**: `GET /api/v1/cost` 改为聚合 new-api 底座真实用量（`GET /api/data/` 按天/模型）；社区版无法诚实推导的「较直连节省 / 缓存 ROI / 优化建议」明确降级为「即将推出」（商业版），绝不编造。
- **Console 商业化文案**: 「审计」收敛为「合规」四支柱；未建能力统一「即将推出」（保留卡片、去开发态字眼）；四目标「划算」统一为「省钱」。

### §D.1 脊柱与底座（gateway 阶段）

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
- `internal-kb` / `vector-db` / `ci-trigger` / `pm-bridge` are real but **single-node, stdlib-only** community implementations (TF-IDF / in-memory hashing-vectorizer / local audit) — distributed retrieval, a trained reranker, and a managed CI/PM bridge are commercial.
- Outbound hallucination detection is **rule-based** (community); the trained classifier is commercial.
- Cost **savings intelligence** (vs-direct, cache ROI, optimization tips) and a hard daily budget cap are commercial; the community cost view is real usage/spend only.
- Real OIDC / multi-tenant / billing are post-1.0.
- Docker image tags in `deploy/.env.production` (`VERSION=0.5.0-edge`) trail the product version pending a maintainer bump.

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
