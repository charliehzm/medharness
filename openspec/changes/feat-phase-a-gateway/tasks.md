# Phase A · 网关焊接 + A0 后端 + Console · 任务拆解

> **设计基线**：[系统设计 01/02/03](../../../docs/system-design/) + [ADR-18](../../../docs/architecture/ADR-18-gateway-control-plane.md)（控制面契约）。
> **分工**：Claude = 拆解 + 异构 code review + 合规 Gate；**Codex-BE** = 后端；**Codex-FE** = 前端。
> **铁律**：每任务 **≤2 文件**、单文档、依赖序执行；A0 契约（v0.7.x · 单 owner=Claude）是 FE/BE **唯一缝**，任一 Codex **不得私改契约**——需改提给 Claude bump。
> **已继承（无需重做）**：B1 tier 签名（`mcp/model-router/tier_trust.py` + PolicyCore layer-0）、H2 错误脱敏、M1 审计降级、A0 契约 v0.7.0。
> **DoD 通用**：① 该任务测试绿 + 不破坏 367 全量 ② ruff/tsc 过 ③ 触 L3/L4 路径有 0-PHI 验收 ④ 经 Claude 异构 review 关闭。

---

## 0. 外部门禁（开工前 / 交付前必须，非 Codex 可解）
- **B6** ✅ **已满足**：new-api **完全授权已获**（2026-05-31）——fork / 入仓 / 对外交付**不再受阻**，关键路径解压；仅留 SBOM 记账（BE-0 顺手）。
- **B4** fork 上 pre-call 延迟 POC（p50/p95/p99）——**BE-7 后立即跑**，未达标收紧 lane 或降级 SLO 文案。
- **B5** 核 new-api 用户/令牌/渠道 **精确字段集**（定 admin 代理白名单粒度）——**BE-6b 前**由 Claude+BE 核。

---

## 后端轨（Codex-BE）· 依赖序

| # | 任务 | 文件(≤2) | 依赖 | DoD 关键验收 |
|---|---|---|---|---|
| **BE-0** | **fork/vendor new-api 入仓** + 基线编译 + 移除转售模块（禁用开关·ADR-18 §5）· *infra 大任务·免 ≤2 文件* | `vendor/new-api/`（fork 子树）· `deploy/docker-compose.prod.yml` | —（**B6 已满足 → 立即开**，∥ BE-1）| fork 起得来；自助注册/支付/订阅/兑换/充值/钱包/社交登录 不可达；SBOM 出；上游 rebase 友好 |
| **BE-1** | ClickHouse + Redis 入 compose + 卷/网/健康 | `deploy/docker-compose.prod.yml` · `deploy/.env.production.example` | — | compose up 起 CH/Redis；audit-log/desensitize 健康连真 CH（非 mock） |
| **BE-2** | audit-log 接真 ClickHouse（去 mock）+ 哈希链落表 | `mcp/audit-log/clickhouse_writer.py` · `mcp/audit-log/server_v2.py` | BE-1 | 写入 `_audit_log`、daily verify 通过；CH 故障 → FALLBACK 续链；query 返 `{degraded}` |
| **BE-3** | desensitize 接真 CH `_phi_lookup` + KMS/FileKeyProvider 配置化 | `mcp/desensitize/server_v2.py` · `mcp/desensitize/key_provider/file_provider.py` | BE-1 | 信封落 `_phi_lookup`（仅密文）；反查需授权；轮换 `key_generation` 落表 |
| **BE-4** | 控制面服务 HTTP 接口（ADR-18 §4：超时/重试/熔断/fail-closed）· 逐服务 | 每服务 `*/server_v2.py`（拆 5 个子任务，各 1 文件）| BE-2/3 | phi/desens/router/inj/outbound 各暴露 `POST /<op>`；失败 fail-closed；契约化 |
| **BE-5** | A0 后端骨架（FastAPI）+ `/posture` `/traffic` `/events` | `mcp/a0-api/app.py` · `mcp/a0-api/serializers.py` | BE-2,BE-4 | 读 CH/router 聚合；**字段白名单序列化**；安全事件 `payload:null`；过 `assertNoPhi` 等价 |
| **BE-6** | A0 `/audit/{ref}` `/upstreams` `/config` `/cost` `/channels` + `/audit/export` `/config/propose` | `mcp/a0-api/routes_*.py`（拆 2 子任务）| BE-5 | 血缘/哈希链；propose 只产 approval_id 不改配置；cost/channels 聚合 0-PHI |
| **BE-6b** | **B5 admin 只读代理** `/admin/{users\|tokens\|channels}` + 字段白名单 | `mcp/a0-api/routes_admin.py` · `web/src/api/contract/*`(Claude bump v0.7.1) | BE-5 · B5 核字段 | 只回 id 哈希/角色/配额/等级/区域，**禁 email/phone/display_name/备注**；红队 `admin-phi-exfil` 0 命中 |
| **BE-7** | **内置 Go 合规中间件**焊 §D.1 + tier_sig 签发（fork 已在 BE-0 入仓）| new-api fork `relay/middleware_compliance.go`(+1) | **BE-0 · BE-4** | 全 `/v1/*` 必经中间件；pre①②③④→base→post⑥；中间件签 tier（model-router 已验签 B1）；非流式 |
| **BE-8** | 底座禁用清单 + 杀裸 `/api/route` + egress allowlist（ADR-18 §5）| `deploy/nginx/medharness.conf` · new-api fork config | BE-7 | 对外仅 fork `/v1/*` + A0 `/api/v1/*`；裸 MCP 内网封死；**集成测试「deny→provider 0 连接」** |
| **BE-9** | 出站 B1 最小集成（phi_scan 注入 outbound-safety）焊入 ⑥ | `mcp/outbound-safety/classifier.py` · 中间件 hook | BE-7 | post-call 扫 PHI 回流；PHI-lane 缓冲后放；H7 |

> BE-4/BE-6 标「拆 N 子任务」=Codex 每次只做一个服务/一组端点，仍 ≤2 文件。

---

## 前端轨（Codex-FE）· 可立即在 mock 上并行

| # | 任务 | 文件(≤2) | 依赖 | DoD 关键验收 |
|---|---|---|---|---|
| **FE-1** | 设计 token → CSS vars（ui-design §2 配色/字号/间距）| `web/src/styles/tokens.css` · `web/src/styles.css` | — | navy/teal/violet/cost + lane 色；与原型一致 |
| **FE-2** | 组件库（映射原型：Card/Tag/Ring/Table/双色 EventStream）| `web/src/components/*`（拆 2-3 子任务）· — | FE-1 | 与原型视觉一致；Semi 可选；Storybook/样例 |
| **FE-3** | 应用壳 SideNav+TopBar + 路由 + **RBAC 2 角色灰显** | `web/src/app/AppShell.tsx` · `web/src/app/nav.ts` | FE-2 | 7 视图 IA；系统管理员 流量/审计/策略 灰显🔒；落点正确 |
| **FE-4** | api-client：`fetch→assertNoPhi→Sanitized<T>` + mock/真切换 | `web/src/api/client.ts` · — | — | 默认 mock（resolveMock）；任何响应必过守卫；错误体不显栈 |
| **FE-5** | 🏠 总览（四目标卡 + 6 闸门 + 需要注意 + 本月小结）on mock | `web/src/views/Overview.tsx` · — | FE-3,FE-4 | 跑 `/posture` mock；`built:false`→🚧；与原型一致 |
| **FE-6** | 📊 流量监控（双向桑基 VChart + 双色事件流 + 三态过滤）| `web/src/views/Traffic.tsx` · `web/src/components/Sankey.tsx` | FE-5 | 出站 `built:false`→🚧；安全事件无 payload；粒子流向 |
| **FE-7** | 🔍 审计与报表（事件流 + 检索 + 血缘+哈希链抽屉 + 导出）| `web/src/views/Audit.tsx` · — | FE-5 | `/audit/{ref}` 血缘+链；导出走 `/audit/export`；占位符 prompt |
| **FE-8** | 💰 用量与成本（KPI + 通道/模型构成 + 比价 + 护栏 + 省钱建议）| `web/src/views/Cost.tsx` · — | FE-5 | 跑 `/cost`+`/channels`（v0.7.0）；聚合 0-PHI |
| **FE-9** | 🔌 接入（应用/渠道/令牌/**用户经 A0 admin 代理**）| `web/src/views/Access.tsx` · — | FE-5 · BE-6b | 读走 A0 admin 代理（非直调 new-api）；**无转售入口**；写走审批 |
| **FE-10** | ⚙️ 策略（合规/安全/成本护栏/治理审批 + DIFF + 审批弹窗）| `web/src/views/Policy.tsx` · — | FE-5 | `/config/{section}`；propose 只提交审批；2 角色矩阵 |
| **FE-11** | 🛠 系统 + 🔐 登录页（科技感 · OIDC/passkey 无自助注册）| `web/src/views/System.tsx` · `web/src/views/Login.tsx` | FE-3 | 部署健康；登录后按角色落点；移植原型登录视觉 |

> FE 全程默认 mock + `built:false` 横幅，不被 BE 阻塞；A0 真端点 ready 后切真即可（M3）。

---

## 并行与里程碑
- **可立即并行**：FE-1..FE-5（mock）+ **BE-0（fork 入仓 · B6 已满足）** + BE-1..BE-6 互不阻塞（缝=A0 契约）。
- **BE 关键路径**：BE-0/1→2/3→4→5/6→7→8→9（B6 已解，中间件焊接不再等授权）。
- **会合点**：A0 真端点 ready → FE 切真 + Claude 跑 0-PHI 回归。
- **Phase A 出口**：BE-8 集成测试「deny→0 连接」绿 + **B4 延迟达标** + **r3 异构复审** → 异构闸门 WAIVED→签字。（B6 已满足。）
