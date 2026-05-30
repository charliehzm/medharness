# 系统设计 · Codex 异构复审 r1 · 处置记录

> **复审者**：Codex（与主线设计模型**异构** · 不同厂商），按 [CODEX_REVIEW_PROMPT.md](CODEX_REVIEW_PROMPT.md) 执行。
> **总评**：**有条件推进（Go-with-changes）**——四目标拆分、ADR-11 下沉网关、new-api fork + 内置 Go 中间件焊 §D.1 方向可落地；但 🔴 项不修不能进 Phase A 编码。
> **处置体例**：仿 RFC r2「纳 PR #107 Codex 三条阻断项」。本表逐条记账：✅ 已修（设计层）/ 📌 backlog（Phase A 交付物）/ 💬 澄清。
> **结论**：6 阻断 + 7 高 全部**接受**。
> ⚠️ **更正（见 [r2 代码级复审](REVIEW-r2-codecheck.md)）**：本表把 B2/B3 记为「✅ 设计层已修」**偏乐观**——ADR-18 是设计承诺，v0.5 **代码仍信任客户端自报分级**（r2 实查 `server_v2.py:187/195` + `policy.py:151` 确认）。B2/B3 改读为「设计已定 · **代码待改（Phase A 阻断）**」；异构复审状态 = **FAIL / WAIVED**，未签字。

---

## 阻断（Blocking）— 不修不能进 Phase A

| # | 要点 | 处置 | 落点 |
|---|---|---|---|
| **B1** | 脊柱现网可绕过：nginx 仅代 `/api/route`→model-router，裸 MCP 可被客户端直调，跳过 ①phi②脱敏④注入 | ✅ Phase A **第一提交门禁**：只暴露 fork `/v1/*`，**撤掉/内网封死裸 `/api/route`**，egress 仅经 fork | [01 §9](01-architecture.md) Phase A 门禁 · [ADR-18](../architecture/ADR-18-gateway-control-plane.md) §5 |
| **B2** | `RouteDecision` 是设计 fiction：`policy.py` 仅输出 decision/reason/layer_failed/policy_version/duration_us，且只裁单个 model_id；不变量②③代码层无法 enforce | ✅ **ADR-18 冻结目标 schema**（`allowed_model_set[]`+`lane`+`max_data_level`）；PolicyCore Phase A 必须扩；中间件禁用客户端 model_id 直选渠道 | [ADR-18](../architecture/ADR-18-gateway-control-plane.md) §2 · [02 §2.2/§4](02-backend-design.md) 标注代码差距 |
| **B3** | 信任客户端自报 `data_level`/`desensitized`：可 L4 标 L1 + desensitized:true 走常规/境外 | ✅ 分级/lane/map_id **仅由 Go 中间件在 ①② 后写入签名 RouteDecision**（HMAC/内部 JWT）；PolicyCore **拒收**客户端自报分级 | [ADR-18](../architecture/ADR-18-gateway-control-plane.md) §3 · [02 §4](02-backend-design.md) |
| **B4** | §G.2 延迟预算未与实现闭环：串行 Presidio+脱敏+路由+注入 的 p95≤35ms 未证明；控制面无统一 HTTP 契约 | ✅ Phase A **前置 mandatory POC**：fork 上实测 p50/p95/p99；未达标收紧为「PHI-lane 缓冲 + clean-lane rule-only」或降级 SLO 文案。承诺软化 | [01 §9](01-architecture.md) · [02 §10](02-backend-design.md) POC 门禁 |
| **B5** | 管理面绕开 0-PHI 双层守卫：接入屏直调 new-api users/tokens/channels，不经 A0、assertNoPhi 不覆盖 | ✅ 管理**读**经 **A0 代理 + 字段白名单**（只回 user_id 哈希/角色/配额），或 FE 对 new-api 响应跑同口径 assertNoPhi + 禁 email/phone；写仍走审批 | [03 §10](03-frontend-design.md) · [02 §6](02-backend-design.md) A0 加管理只读代理 |
| **B6** | new-api AGPL 依赖「商业授权兜底」未落地 | ✅ **已满足（2026-05-31）**：new-api **完全授权已获** → fork / 对外交付不再受阻；仅留 SBOM 记账 | [01 §9](01-architecture.md) |

## 高（High）

| # | 要点 | 处置 | 落点 |
|---|---|---|---|
| **H1** | 「超级→改路由敏感通道」仅实现 deny 一半，无 reroute/重算 set | ✅ PolicyCore 增 `reroute(lane=sensitive)` 结果或中间件二次 evaluate | [ADR-18 §2](../architecture/ADR-18-gateway-control-plane.md) · [02 §4](02-backend-design.md) |
| **H2** | 「不出境」无 region/lane：allowlist 仅 deployment 串，PolicyCore 不解析 private:// vs 境外 | ✅ allowlist 增 `region/egress_zone`；PolicyCore 层⑥校验 lane×region | [ADR-18 §2](../architecture/ADR-18-gateway-control-plane.md) · [02 §5.3](02-backend-design.md) |
| **H3** | §D.1 五不变量在 fork 上无 enforcement 细节，未列必须禁用的 new-api 能力 | ✅ ADR-18 附**底座禁用清单**（内置 cache/自动切换/relay 旁路/前置 access 日志）+ 集成测试「deny 后 provider 0 连接」 | [ADR-18 §5](../architecture/ADR-18-gateway-control-plane.md) |
| **H4** | 流式 SSE 与不变量④冲突（半句 PHI 已吐），Phase A 未设门禁 | ✅ **Phase A 仅非流式**；流式进 Phase B + ADR-19；fork 默认关流式或 PHI-lane 全缓冲 | [01 §9](01-architecture.md) · [02 §9](02-backend-design.md) |
| **H5** | BACKFILL 期 append 硬失败 → 若「审计失败仍放行」= fail-open | ✅ 定义**审计不可用 = deny**（或异步队列满则 deny）；BACKFILL 与实时写分离 | [02 §9](02-backend-design.md) |
| **H6** | C2 命名漂移：表列独立 gate-orchestrator，正文已决内置中间件 → 易双轨漏洞 | ✅ 全文统一 **C2 = relay middleware only**，删 orchestrator 独立服务表述 | [01 §3](01-architecture.md)（本轮已统一） |
| **H7** | 出站 B1 标 🟡 规则态，但 §D.1 ⑥ 为脊柱一环；与「双向网关」叙事冲突 | ✅ **Phase A = 入站为主**：⑥ 最小 B1（phi_scan 注入）或文档降级「入站-only Phase A，出站 Phase B」 | [02 §10](02-backend-design.md) · [01 §9](01-architecture.md) |

## 中（Medium）

| # | 处置 |
|---|---|
| **M1** L1 强迫 desensitized:true | ✅ 中间件：无 span→`desensitized=false`+L1；有 span→脱敏后才 true（[ADR-18 §3](../architecture/ADR-18-gateway-control-plane.md)） |
| **M2** 组件状态表过度乐观 | ✅ [01 §3](01-architecture.md) 加「网关路径/焊接」子状态，区分「内核 ✅」vs「网关路径 ✅」 |
| **M3** A0 后端全 🔴 但 FE 依赖真数据，契约超前 | 📌 backlog：Phase A 子里程碑 A0 8 端点先于 F2；否则 FE 强制 mock + `built:false` 横幅（[03 §11](03-frontend-design.md) 已含 mock 默认） |
| **M4** sanitize 模式不全（缺 MRN/中文姓名/DOB） | 📌 backlog：与 `drill_api_phi_exfil.py`/`fields.yml` 28 实体同步；过渡期 FE 仅允许 `__*_`/`routing#` 串 |
| **M5** fail-closed「或落敏感通道」语义模糊 | ✅ [02 §9](02-backend-design.md) 写清优先级：**不确定 = deny**；仅「已脱敏但 lane 模糊」可 sensitive |
| **M6** r5 后仍有 slim 残留措辞 | ✅ 全文检索统一（r5 已主改；本轮复核 system-design 无 slim 残留） |
| **M7** internal 网无 egress allowlist 实施 | 📌 backlog：Phase A 交付物含 egress-allowlist 可测配置（iptables/sidecar） |

## 低 / 改进（Low）

| # | 处置 |
|---|---|
| **L1** 03 仍写「需会签确认」 | ✅ [03 §1](03-frontend-design.md) 删（自建已确认） |
| **L2** 伪码缺第二处 audit.Log | ✅ [02 §2.1](02-backend-design.md) 伪码注「外呼后写」 |
| **L3** endpoints.ts 注释「GET×6」应 GET×8 | ✅ [endpoints.ts](../../web/src/api/contract/endpoints.ts) 注释修正 |
| **L4** BACKFILL 后全链 verify 测试 | 📌 backlog：进 [02 §10](02-backend-design.md) Phase A 验收清单 |
| **L5** A0 聚合勿 join 含原文日志表 | 💬 [02 §6](02-backend-design.md) 红线已含「字段白名单」；强调 A0 实现**禁 SELECT 非白名单列** |

---

## 待进一步验证（Codex 标注 · Phase A POC 期核实）
1. new-api 全部 relay 分支（含 image/midjourney/video）是否**必经**合规中间件——需逐路径核 + 集成测试。
2. new-api 用户/令牌 API 的**精确字段集**（是否含 email/display_name/备注）——决定 B5 白名单粒度。
3. egress allowlist 脚本是否在仓库外——Phase A 须纳入交付。

## 复审回收动作
- 🔴×6 + 🟠×7 → 已落 [ADR-18](../architecture/ADR-18-gateway-control-plane.md) + 01/02/03 修订（见各落点）。
- 📌 backlog（M3/M4/M7/L4）→ 进 Phase A change 的 tasks.md，指派 owner。
- 本记录 + Codex 原始 finding 归档进 AUDIT_BUNDLE（audit-snapshot Skill）。
- **Phase A 准入** = 本表全部 🔴 已 resolved + ADR-18 技委/合规委会签 + B4 POC 达标（B6 授权已获）。
