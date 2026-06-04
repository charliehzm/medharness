# Codex 异构复审提示语 · MedHarness 系统详细设计

> **用法**：把下面 `===== PROMPT =====` 之间整段贴给 Codex（需给它本仓库的读权限）。Codex 与主线设计模型**异构**（不同厂商），这正是本项目合规纪律要求的"复审/合规用异构模型、防自证清白"（参 PR #107 Codex 复审先例、compliance-review Skill）。
> **复审对象**：`docs/system-design/`（01 架构 / 02 后端 / 03 前端）+ A0 契约代码 + 控制面代码现状。
> **本轮三决策（复审须按此为前提）**：① A0 加 `/cost`+`/channels`（v0.7.0）；② gate 编排 = new-api **内置 Go 中间件**（进程内）；③ 前端**自建**（复用 new-api 后端非前端）。

---

===== PROMPT =====

你是一名资深系统架构师 + 医疗数据合规安全审计员，受邀对 **MedHarness**（医疗大模型流量网关）的系统详细设计做一次**独立异构复审**。你与撰写该设计的模型来自不同厂商——请用**怀疑的、找茬的**视角，不要客套、不要 rubber-stamp。你的复审会进入合规审计留痕。

## 0. 背景（30 秒）
MedHarness = **new-api 深度 fork（Go 网关底座）** + **合规控制面（6 个 Python 服务：phi-detector/desensitize/model-router/audit-log/injection-scan/outbound-safety）** + **ClickHouse/Redis/KMS** + **自建 React Console（经 A0 只读聚合 API 读数，全程 0 PHI）**。四目标：**安全 · 划算 · 审计 · 稳定**。红线：HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南；**L4 PHI 永不裸出境、模型按 allowlist 路由、全量审计、fail-closed 优先于省钱与可用**。

## 1. 先读这些（按序）
1. `docs/system-design/01-architecture.md` — 运行态架构、组件清单、**§4 Hook 强制顺序契约（脊柱）**、L1–L4 分级、0-PHI 边界、部署拓扑。
2. `docs/system-design/02-backend-design.md` — 网关焊接(§2)、控制面服务、**PolicyCore 5 层(§4)**、数据模型、A0 后端(§6)、fail-closed(§9)。
3. `docs/system-design/03-frontend-design.md` — 前端自建(§1)、A0 契约层+`Sanitized<T>`守卫(§3)、逐屏↔端点映射(§7)、管理面集成(§10)。
4. 契约代码：`web/src/api/contract/{types.ts,endpoints.ts,version.ts,mock.ts,sanitize.ts}` + `fixtures/`。
5. 对照真实代码：`mcp/model-router/policy.py`、`mcp/audit-log/{hashchain.py,server_v2.py}`、`mcp/desensitize/crypto_envelope.py`、`deploy/docker-compose.prod.yml`、`deploy/nginx/medharness.conf`、`docs/architecture/gateway-substrate-selection.md`(RFC r4/r5)。
6. 设计基准：`prototype/console-demo.html`。

## 2. 复审维度（逐条给结论）
1. **架构健全性**：组件划分、依赖、单主机拓扑是否自洽？new-api fork + 控制面 + 数据存储的边界是否清晰？
2. **§D.1 脊柱可强制性**（最高优先）：pre-call(①检测→②脱敏→③路由→④注入) → 底座(cache/retry/dispatch/log) → post-call(⑥出站) 这条顺序，**用 new-api 内置 Go 中间件实现，是否真能保证 5 条不变量**（deny 即静默 / 底座无自主权 / fallback 不越 `allowed_model_set` / 缓存只在 gate 后 / 审计前后双写）？**有没有任何绕过路径**（如 new-api 某条 relay 分支没走中间件、流式 SSE 旁路、缓存命中直返未过 post-call）？
3. **决策②Go 中间件取舍**：进程内 Go 中间件同步串 4–5 个 Python 服务，**是否吃得住 §G.2 延迟预算**（非流式 p95≤80ms、流式 TTFT p95≤50ms）？"inline 仅 rule-first、重 NLP 异步"是否被设计自洽地兑现？fork 维护/rebase 冲突面如何？是否该有降级/超时/熔断契约（开放项②）？
4. **0-PHI 保证**：A0 出参三类内容（占位符/哈希/聚合）+ 安全事件 `payload` 恒 null + `Sanitized<T>`/`assertNoPhi` 双层守卫，**是否真的密不透风**？新加的 `/cost`、`/channels` 是否引入 PHI 面？**特别地**：决策③管理面（接入屏）直接调 **new-api 原生管理 API**（渠道/令牌/用户），**这条路径绕过了 A0 的 0-PHI 守卫**——new-api 的 user/token API 是否可能回吐 PHI/PII（如用户邮箱、原始标识），需要补什么守卫？
5. **PolicyCore 5 层 + 异构**：①脱敏标记 ②allowlist ③agent 角色 ④数据等级 ⑤异构性 的顺序与 fail-closed 是否正确？`allowed_data_levels` 能否被绕过把 L3/L4 路由到境外？
6. **审计不可篡改**：哈希链(`current=SHA256(prev‖canonical(event))`) + WORM + ClickHouse 故障 FALLBACK 续链 + BACKFILL，链在故障/并发下是否可能断裂或被重排？
7. **稳定/fail-closed**：单实例健壮性是否真的"危险请求拒、服务不下线"？哪些故障会让 fail-closed 退化成 fail-open？
8. **doc↔code 一致性**：设计文档与真实代码（mcp/ 服务、契约、compose）有无矛盾或过度承诺（声称已建但实际 stub）？
9. **缺口与排期**：Phase A（fork+中间件+A0 后端+ClickHouse/Redis/KMS）的拆分是否完整？有无被漏掉的落地阻塞项？

## 3. 输出格式（务必结构化）
先给**一句话总评**（可落地推进 / 有条件推进 / 阻断，并说明理由），再按严重度列 findings：

```
### 阻断（Blocking）— 不修不能进 Phase A
- [B1] <file:line 或 §节> — <问题> — <为何违反红线/不变量> — <具体整改>
### 高（High）
- [H1] ...
### 中（Medium）
- [M1] ...
### 低 / 改进（Low）
- [L1] ...
### 复审者也要守的红线
- 你的复审输出本身 0 PHI（只引占位符/哈希/聚合，不要把任何疑似真实标识写进 finding）。
```

要求：每条 finding **引真实 file:line 或 §节号**；区分"设计缺陷"与"实现待办"；对你不确定的点标注"需进一步验证"而非臆断；**优先找能被绕过的 0-PHI 漏点与 §D.1 顺序漏点**——那是本系统的命门。

===== /PROMPT =====

---

## 复审回收（给 MedHarness 团队）
- Codex 的 finding 按本项目惯例：**阻断项**回流改 `docs/system-design/*` 或代码，并在对应 RFC/ADR 记账（参 RFC r2「纳 PR #107 Codex 三条阻断项」体例）。
- 高/中项进 backlog，指派 owner + 整改。
- 复审线程归档进 AUDIT_BUNDLE（compliance-review / audit-snapshot Skill）。
