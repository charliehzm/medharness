# MedHarness 系统架构设计

> **状态**：**定稿 v1（实现基线）** · 内容锁定供实现；异构闸门 WAIVED（待 Phase A B1 代码 + r3 复审）· 双委员会会签 pending
> **范畴**：**产品运行态架构**（客户侧的医疗大模型流量网关），不是本仓库 AI-Coding 研发 harness 的架构（那条见 [../architecture/dependency-graph.md](../architecture/dependency-graph.md) 的 L1–L6）。
> **锚点**：底座 RFC [r4 锁 new-api / r5 单 SKU](../architecture/gateway-substrate-selection.md) · ADR-11「egress 网关是唯一强制点」[../architecture/unified-gateway.md](../architecture/unified-gateway.md) · 四目标 PRD [../productization/product-requirements.md](../productization/product-requirements.md)。

---

## 1. 架构目标（四目标 → 架构责任）

| 目标 | 架构落点 |
|---|---|
| **安全** | 请求/响应必经 **pre-call 4 闸 + post-call 1 闸**；PHI 永不裸出境；模型按 allowlist 路由；注入隔离 |
| **划算** | 数据分级双通道：脱敏后低敏流量走**常规通道（境内低成本池）**，高敏走**敏感通道（私有不出境）**；复用 new-api 渠道加权 + 缓存 |
| **审计** | 每次调用前后全量落 **ClickHouse WORM + 哈希链**；0 PHI（仅占位符/哈希/聚合）；监管应对包 ≤4h |
| **稳定** | 网关附加延迟有界（非流式**目标** p95≤80ms · **待 Phase A POC 证明**，Codex B4）；provider 故障切换（限 allowlist 内）；熔断/限流；**fail-closed 不下线**；ClickHouse 故障 → 文件 fallback 续链 |

> **铁律优先级**：`fail-closed` > 划算 > 可用。任一闸门 fail/超时/不确定 → 默认拒或落敏感通道，**绝不为省钱或保活放行危险请求**。

---

## 2. 逻辑架构（一张图）

```
            ┌─────────────── 客户本地部署（单主机 docker-compose）───────────────┐
 开发态     │                                                                      │
 Claude Code│   ┌────────────┐    pre-call gate（阻塞·rule-first）                 │
 Codex ─────┼──▶│ new-api    │──▶ ① phi-detector → ② desensitize →                │
            │   │ fork       │     ③ model-router(PolicyCore) → ④ injection-scan  │
 生产态     │   │ (Go·HTTP   │         │ 产出 RouteDecision（结构化·底座不可覆写） │
 Dify ──────┼──▶│  网关·     │         ▼  ——— 以下在 gate 之后 ———                 │
 ComfyUI    │   │  OpenAI/   │     ⑤ 缓存查（仅脱敏体）→ ⑥ 渠道择优/重试(限 set) │
 自研业务 ──┼──▶│  Anthropic │     → ⑦ provider dispatch（境内低成本池 / 私有）   │
            │   │  兼容)     │     → ⑧ provider/计费日志                          │
            │   │            │◀── ⑥ post-call gate：outbound-safety（PHI回流/有害/幻觉）│
            │   └─────┬──────┘                                                     │
            │         │ 每步落审计                                                 │
            │         ▼                                                            │
            │   ┌──────────────┐   ┌──────────┐  ┌────────┐  ┌──────────────────┐ │
            │   │ audit-log    │──▶│ClickHouse│  │ Redis  │  │ KMS / FileKeyProv │ │
            │   │ WORM+哈希链  │   │_audit_log│  │ cache  │  │ desensitize 密钥  │ │
            │   │ +fallback    │   │_phi_lookup│ └────────┘  └──────────────────┘ │
            │   └──────────────┘   └──────────┘                                    │
            │                                                                      │
            │   ┌──────────────────────────────────────────────────────────────┐ │
 研发负责人 │   │ MedHarness Console（自建 React 应用）                          │ │
 系统管理员─┼──▶│  └ 经 A0 只读聚合 API（/api/v1/*）读数 · Sanitized<T> 0-PHI 守卫│ │
            │   │  └ 管理面（渠道/令牌/用户）走 new-api 原生管理 API             │ │
            │   └──────────────────────────────────────────────────────────────┘ │
            └──────────────────────────────────────────────────────────────────────┘
```

工程师**不进 Console**：仅把 base_url 指向网关 + 用个人令牌。Console 是研发负责人/系统管理员的控制台。

---

## 3. 组件清单

| # | 组件 | 语言/形态 | 责任 | 现状 |
|---|---|---|---|---|
| C1 | **new-api fork（网关底座）** | Go · HTTP | 协议归一（OpenAI⇄Claude⇄Gemini）、渠道扇出/择优/重试、缓存、计费、用户/令牌/OIDC、relay。**内置 C2 合规中间件**强制 §D.1 | 🔴 **未 fork**（Phase A 核心） |
| C2 | **合规中间件（new-api 内置）** | **Go · 进程内** | 内置于 C1 relay 链的中间件（**已决：Go 内置，非独立服务**）——enforcement 在网关内不可绕过、少一跳。按 §D.1 串 ①②③④(pre)+⑥(post)，HTTP 调 C3–C8 Python 服务，聚合 RouteDecision、全程落审计；inline 仅 rule-first、重 NLP 异步 | 🔴 待建（Phase A） |
| C3 | phi-detector | Python · MCP/HTTP | 入站 PHI 检测（Presidio + 28 实体 + 中文识别器 + 上下文规则） | ✅ v3（recall 1.0 / FP 0.09） |
| C4 | desensitize | Python · MCP/HTTP | AES-256-GCM + AAD 可逆脱敏；FileKeyProvider 多代轮换（云 KMS 预留）；反查表存 ClickHouse `_phi_lookup`（仅密文） | ✅ v2（p99 0.02ms） |
| C5 | model-router | Python · MCP/HTTP | **PolicyCore 5 层 gate** + 异构强制 + 限流/熔断；输出不可覆写的 RouteDecision | ✅ v2（<5ms · 11/11 越权拦） |
| C6 | audit-log | Python · MCP/HTTP | WORM 三态机（NORMAL→FALLBACK→BACKFILL）+ SHA-256 哈希链 + PID lock；ClickHouse `_audit_log` | ✅ v2（链完整·4h 重放） |
| C7 | prompt-injection-scan | Python · MCP/HTTP | 5 类注入检测（不回显 payload） | ✅（阻断率 1.0） |
| C8 | outbound-safety | Python · MCP/HTTP | 出站响应安全（PHI 回流/有害/幻觉医嘱）规则核 | 🟡 v0.5 规则态，phi_scan 集成留 v0.6 |
| C9 | **A0 聚合 API 服务** | Python（拟 FastAPI）· HTTP | 实现 10 个 `/api/v1/*` 端点（**v0.7.0**：含 GET `/cost`、`/channels`）；从 ClickHouse/audit/router/new-api 聚合 → **只出占位符/哈希/聚合**；写口仅产「提交审批」 | 🟡 **契约 v0.7.0，后端未实现** |
| C10 | **Console（web/）** | React 18 + TS + Vite | 控制台 UI；经 A0 读数 + `Sanitized<T>` 守卫；管理面调 new-api API | 🟡 脚手架 + A0 契约层已冻，屏幕待建（F1–F3） |
| C11 | ClickHouse | 单节点 | 审计 `_audit_log`（7y TTL）+ 脱敏反查 `_phi_lookup`（6y TTL）；append-only + WORM | 🔴 未入 compose（Phase A） |
| C12 | Redis | 单节点 | 缓存层（仅脱敏体 + 严格 TTL + 租户隔离） | 🔴 未入 compose（Phase A） |
| C13 | KMS / 密钥服务 | 接口 | desensitize 密钥托管（v0.5 用 FileKeyProvider，云 KMS proxy 留 v1.0） | 🟡 FileKeyProvider 在 |
| C14 | nginx | DMZ 反代 | TLS 终止 + 健康检查 + egress allowlist 边界 | ✅（仅代 `/api/route`、`/api/audit`） |

> **C8 命名澄清**：`mcp-model-router` 是运行态 gate；`compliance-precheck` Skill（研发期 Step 0）生成 `MODEL_ALLOWLIST.json` 注入 C5 作 allowlist —— 二者一个运行态、一个研发态，别混。
> **状态读法（Codex M2）**：C3–C8 标 ✅ 指「内核已建 + 单测过」，**不**代表「网关路径已焊」——经 C1/C2 HTTP 可达的网关路径属 Phase A，未通前 Console 用 mock + `built:false`。

---

## 4. 脊柱：Hook 强制顺序契约（§D.1 · 不可让步）

整个后端架构围绕一条**不可绕过的顺序**展开（出处 [RFC §D.1](../architecture/gateway-substrate-selection.md)）：

```
请求入站
  └─① 合规 pre-call gate（phi-detector → desensitize → model-router → injection-scan）
        产出 RouteDecision{decision_id, lane, allowed_model_set, provider_policy, audit_labels}
        ▼ ——— 以下全部发生在 gate 之后 ———
     ② 底座 cache 查询      （命中也不得返回未过 gate 的体；key/value 仅脱敏体）
     ③ 底座 retry / fallback（只在 decision.allowed_model_set 内，不得越权）
     ④ 底座 provider dispatch（实际外呼，限 egress allowlist）
     ⑤ 底座 provider logging（落上游/计费日志）
  └─⑥ 合规 post-call gate（outbound-safety 出站扫描）→ 才返回调用方
```

**不变量（架构级红线）**：
1. **deny 即静默**：pre-call 判 deny → 不外呼、不写 cache、不落上游日志，直接合规拒绝 + 审计。
2. **底座无自主权**：new-api 只**执行** RouteDecision，无自主选模型 / 跨 lane / 跨 allowlist 的能力；成本排序仅在 `allowed_model_set` 内。
3. **fallback 不越权**：失败重试/降级**只能**在 `allowed_model_set` 内，永不回退集合外 provider。
4. **缓存只在 gate 之后**：cache 仅含脱敏体；命中也必须过 post-call gate 再回。
5. **审计前后双写**：外呼**前后**均有 audit 记录，哈希链可重放。

> 🔴 **当前缺口**：v0.5 的 MCP 服务是 stdio 内部服务，nginx 仅代 `/api/route`、`/api/audit`，**没有任何 HTTP 网关在边界强制以上顺序**。Phase A = fork new-api + **内置 Go 合规中间件（C2，已决：进程内，非独立服务）** 把这条顺序焊死在 relay 链上——enforcement 在网关内、不可绕过、少一跳。顺序契约 + 签名 RouteDecision + 底座禁用清单见 [ADR-18](../architecture/ADR-18-gateway-control-plane.md)（Codex r1 B1/B2/B3）。**这是落地第一优先级**。

---

## 5. 数据分级（L1–L4）与双通道路由

| 级 | 内容 | 入 prompt | 路由 | 通道 |
|---|---|---|---|---|
| **L1 公开** | 无标识 | ✅ | 任意（allowlist 内） | 常规通道 |
| **L2 内部** | 非 PHI 内部（设计/配置/非临床） | ✅ | 受限 allowlist | 常规通道 |
| **L3 敏感** | 去标识临床（诊断码/治疗，无身份） | ✅（脱敏后） | 收紧 allowlist · 不出境 | 敏感通道 |
| **L4 高敏 PHI** | 原始标识（姓名/身份证/病案号/完整 DOB） | ❌（必先脱敏） | 私有/境内 only | 敏感通道 |

**脱敏是桥**：desensitize 把 L4 → L1/L2 占位符体，使低敏流量**有资格**安全走常规通道（境内低成本池），这正是「划算」的来源。L3/L4 带 PHI 永不出境。分级判定在 model-router PolicyCore（[mcp/model-router/policy.py](../../mcp/model-router/policy.py)），allowlist 的 `allowed_data_levels` 逐模型约束可承载的最高级。

---

## 6. 0-PHI 信任边界（哪里能有 PHI，哪里绝不能）

| 位置 | 可含 PHI？ | 机制 |
|---|---|---|
| 客户原始请求体（入网关前） | 是（不可避免） | 网关入站立即 ① 检测 ② 脱敏 |
| pre-call gate 之后的一切（cache/provider/上游日志） | **否** | 只流转脱敏占位符体 |
| 常规通道 provider（境内低成本池） | **否** | 仅脱敏体；且限境内 |
| ClickHouse `_audit_log` | **否** | 仅 action/result/哈希/占位符 |
| ClickHouse `_phi_lookup` | 仅**密文** | AES-256-GCM 信封，无明文反查表 |
| **A0 API 响应 → Console** | **否** | 字段白名单序列化 + 安全事件 `payload` 恒 null + `Sanitized<T>`/`assertNoPhi` 运行时守卫 |
| 反查原文 | 受控环境单独授权 | **不在 Console 内**；走 desensitize 解密 + 三签 |

---

## 7. 部署拓扑（现状 → 目标）

**网络**（[deploy/docker-compose.prod.yml](../../deploy/docker-compose.prod.yml)）：`medharness_dmz`（nginx 443）+ `medharness_internal`（internal:true，控制面隔离，不直连上游）。

| 服务 | 现状 compose | 目标（Phase A 后） |
|---|---|---|
| nginx DMZ | ✅ | ✅ + 代 `/v1/*`（网关）`/api/v1/*`（A0） |
| phi-detector / desensitize / model-router / audit-log / injection / outbound | ✅（部分 stub） | ✅ 全活 + HTTP 暴露给 C2 |
| **new-api fork** | 🔴 | ✅ 网关底座 |
| **gate-orchestrator** | 🔴 | ✅ pre/post 编排 |
| **A0 API 服务** | 🔴 | ✅ 8 端点 |
| **ClickHouse / Redis / KMS** | 🔴 | ✅ 单节点 |
| **Console（web/ 构建产物）** | 🔴 | ✅ nginx 静态托管 |

**最低资源**（PRD §6 待 POC 校准）：≥4 vCPU / 8GB / 50GB。**范围外**（→v1.0）：HA/多副本/自动 failover、k8s/helm、Prometheus/Grafana 全栈、多租户、托管 SaaS。

---

## 8. 技术栈总览

| 层 | 选型 | 出处 |
|---|---|---|
| 网关底座 | **new-api**（Go · AGPL，商业授权兜底） | RFC r4 |
| 控制面 | Python 3.12（6 服务）+ Presidio + AES-256-GCM | mcp/ |
| 审计/反查 | ClickHouse（append-only + WORM + 哈希链） | mcp/audit-log, mcp/desensitize |
| 缓存 | Redis（仅脱敏体） | Phase A |
| A0 API | Python（拟 FastAPI · GET×8 + POST×2 · 契约 v0.7.0） | web/src/api/contract/ |
| Console | React 18 + TS + Vite + react-router（+ 设计 token/组件/VChart 待建） | web/ |
| 部署 | 单主机 docker-compose + nginx DMZ | deploy/ |

---

## 9. 落地分期与缺口（诚实护栏）

| 阶段 | 内容 | 状态 |
|---|---|---|
| **v0.5.0-edge（已建）** | 6 控制面服务内核 + 337 测试 + 4 红队演练 + 容器化 + A0 契约冻结 + Console 脚手架 | ✅ |
| **Phase A（落地第一优先级）** | fork new-api + **内置 Go 中间件焊接 §D.1（[ADR-18](../architecture/ADR-18-gateway-control-plane.md)）** + 杀裸 `/api/route`（B1）+ ClickHouse/Redis/KMS 入 compose + A0 后端（含管理只读代理 B5） | 🔴 待建 |
| **Phase B** | 流式 SSE 边扫边转 + outbound-safety 全集成 + Console F1–F3 屏幕 | 🟡 |
| **v1.0** | HA/多副本/failover + 云 KMS proxy + 多模态 PHI（DICOM/影像）+ 语义重放 | ⏭️ |

> **诚实声明**：v0.5「PoC-grade not SLA-grade」。本架构「稳定」指**单实例健壮性**，不等于 HA。合同/客户沟通须讲清。

> **Phase A 准入门禁**（Codex 异构复审 r1 阻断项 · 全绿才进编码 · [处置记录](REVIEW-r1-codex.md)）：
> 1. **B1 杀脊柱旁路**：对外只暴露 fork `/v1/*`，撤掉/内网封死裸 `/api/route`；所有 relay 子路由必经中间件（集成测试「deny → provider 0 连接」）。
> 2. **B4 延迟 POC**：fork 上实测 pre-call p50/p95/p99；未达 §G.2 预算则收紧为「PHI-lane 缓冲 + clean-lane rule-only」或降级 SLO 文案——**未证明前不对外宣称 p95≤80ms**。
> 3. **B6 ✅ 已满足**：new-api **完全授权已获**（2026-05-31）——fork / 对外交付不再受阻；仅留 SBOM 记账。
> 4. **H4 仅非流式**：Phase A 不上流式 SSE（半句 PHI 风险）；流式 → Phase B + ADR-19。
> 5. **H7 出站**：Phase A 至少最小 B1（phi_scan 注入）焊入 ⑥，否则四目标表降级「入站-only Phase A」。
> 6. **ADR-18 会签**：RouteDecision 签名 schema + 底座禁用清单冻结（[ADR-18](../architecture/ADR-18-gateway-control-plane.md)）。
> 7. **B1/H2/M1 代码 enforcement（r2）✅ 已闭环（2026-05-31）**：model-router tier HMAC 签名 + PolicyCore layer-0 fail-closed（拒客户端自报分级）、错误体 sanitize、审计降级显式化——回归测试 + 367 全量 + api-phi-exfil drill 绿（见 [REVIEW-r2 本轮整改](REVIEW-r2-codecheck.md)）。
>
> **异构复审状态 = 维持 WAIVED**：in-repo 安全 findings 已全 **CLOSED**（B1/H2/M1/H3）；剩 **B4**(需 fork 实测)/**B5**(需 new-api 字段 + A0 后端) 外部门禁（**B6 已满足**）+ **r3 复审**确认运行态闭环，才升正式签字。

---

## 10. 关键架构决策与开放项

- **ADR-11**：egress 网关是唯一强制点（已定）。
- **RFC r4**：底座锁 new-api 深度 fork（商业授权兜底）。
- **RFC r5**：单 SKU（≤30 人小厂全栈安全形态）。
- **拟 ADR-18**：OSS 底座 + 控制面 hook 化（new-api relay 焊入点 + **内置 Go 合规中间件**）—— 待技委会签。
- **拟 ADR-19**：数据分级条件路由 + 流式出站扫描取舍 —— 待会签。
- **已决（本轮）**：① gate 形态 = **new-api 内置 Go 中间件**（进程内强制 §D.1，省一跳、不可绕过）；③ 前端 = **自建 React 应用**，管理面调 new-api 原生 API（不 fork 其前端，见 [03](03-frontend-design.md) §1）；A0 **加性 bump v0.7.0** 加成本端点（`/cost`、`/channels`）。
- **仍开放**：② 控制面 Python 服务对 Go 中间件暴露的统一接口规范（HTTP/JSON vs gRPC + 超时/重试/熔断契约）—— 落 ADR-18；④ 流式 SSE 下 §D.1 边扫边转实现 —— Phase B。

详细后端/前端设计见 [02-backend-design.md](02-backend-design.md) / [03-frontend-design.md](03-frontend-design.md)。
