# 系统设计 · 异构复审 r2（代码级 · FAIL）· 处置记录

> **复审者**：第二个异构模型（与 r1 / 主线设计均不同厂商）。**实跑** `api-phi-exfil`：10 fixtures / 266 strings → `passed=true`、`phi_hits=[]`、`payload_violations=[]`；`git log --grep="real PHI|production data|customer name"` 为空。
> **总评**：**阻断（FAIL）**——**不同意**把当前 **WAIVED** 升为正式异构签字。理由：运行态 gate 仍可被 caller 伪造（B1，已实代码核实）+ Console 仍有一条直通 new-api 管理面的 0-PHI 绕口（H1）。
> **drill 通过 ≠ 闭环**：只证明**合成 fixture 干净**，不代表运行态闭环已封死。
> **对 r1 的纠正（诚实）**：[REVIEW-r1](REVIEW-r1-codex.md) 把 B2/B3 记为「✅ 设计层已修」**偏乐观**——ADR-18 是**设计承诺**，v0.5 **代码仍信任客户端自报分级**（本轮实查确认）。**设计 ≠ enforcement**。据此降级。

---

## 我方 trust-but-verify（已读真实代码核对）

| Finding | 评级 | 实查结论（含行号） | 处置 |
|---|---|---|---|
| **B1** caller 可伪造分级 / lane / 异构 | 🔴 **确认真实** | `server_v2.py:187` 取 `desensitized`、`:189-190` 取 `caller_vendor_family`、`:195` 取 `data_level` **全来自 payload**；`policy.py:151-153 _has_desensitized_marker` 直接信任 `request.metadata["desensitized"]`。→ **L4 可标 L1 + desensitized:true 走常规 lane**，根因确凿 | **重归类为 Phase A 代码阻断**（非设计层已修） |
| **H2** 错误体外泄内部细节 | 🟠 **确认真实** | `server_v2.py:245` `error={"message":message}`；`:309` / `:376` 把 `reason`（含 `agent_role`/`change_id`/`circuit open …`/`layer_failed`）回给调用方，违反契约「msg 不得含版本/栈/路径」 | 可现在修：`sanitize_error(code, exc)` 对外只给稳定 code + generic msg，detail 留 audit |
| **H3** 0-PHI 守卫模式不全 | 🟠 **确认真实** | `sanitize.ts:51` 仅 ID/phone/email/bank/passport + payload≠null，**无 MRN / 中文姓名 / DOB**；r1 M4 自认 backlog → 现宣称「全程 0 PHI」**过宽** | 现在修：**收窄口径**（守卫是「防回显」非「PHI 全检」，0-PHI 以后端字段白名单为准）+ 排期补 detector/fixtures/corpus |
| **H1** 管理面 0-PHI 绕口 | 🟠 **部分已改 · 待验证** | r1 已把**读**改走 A0 代理（[03 §10](03-frontend-design.md)）；但 new-api 用户 API **精确字段集未核**，**写**仍直调 | 待核 new-api 字段 + 补 assertNoPhi + 白名单测试；核实后 H1 可降级 |
| **M1** 审计坏掉伪装空态 | 🟡 接受 | `audit-log/server_v2.py:131` query 异常返 `[]`、`:213` recover 无强制回放后验链 | Phase A：显式 `degraded` 状态 + post-backfill 全链 verify |
| **M2** RFC 旧裁决痕迹并存 | 🟡 接受 | `gateway-substrate-selection.md` §A/§E one-api/LiteLLM/new-api 旧分析虽有 r4/r5 覆盖标，仍读如三套答案——会签可读性问题（非安全洞） | 会签前收口（折叠或明确围栏超越分析） |

## 待进一步验证（复审者标注 · Phase A POC 期核）
1. new-api 全部 relay 分支（image/midjourney/video）是否**必经**中间件。
2. new-api 用户/令牌/渠道 API 的**精确字段集**（是否含 email/display_name/备注）——决定 H1 白名单粒度。
3. `route_v2` 前是否有未纳入本次范围的 shim 先剥 `desensitized`/`caller_vendor_family`——本次无证据，**先按开放漏洞计**。

## ✅ 本轮代码整改（in-repo findings 闭环 · 测试验证 2026-05-31）

| Finding | 状态 | 代码 + 测试证据 |
|---|---|---|
| **B1** caller 伪造分级 | ✅ **CLOSED** | 新增 `mcp/model-router/tier_trust.py`（HMAC 签 tier）；`server_v2._build_request` 验签 → `metadata.tier_trusted`；`policy.py` 加 **layer-0**：未签即 `deny(tier)`。回归测试 `test_unsigned_tier_denied` / `test_forged_tier_denied`。**全套 model-router + 367 全量测试 + api-phi-exfil drill 绿。运行态 gate 不再可伪造。** |
| **H2** 错误体外泄 | ✅ **CLOSED** | `server_v2._error_response` 外发 generic msg + stable code，detail 仅留 audit；测试改为校验 detail 在审计、`error.message` 不含 tier 值。 |
| **M1** 审计降级伪装空态 | ✅ **CLOSED** | `audit-log/server_v2.query()` 改返 `{degraded,state,rows}` 信封，降级不再伪装空数据。 |
| **H3 / M4** 0-PHI 守卫口径 | ✅ **CLOSED（收口）** | 「全程 0 PHI」已收窄为「防回显护栏 · 0-PHI 以后端字段白名单为准」；前端**不**加会误报的中文姓名/DOB 正则（会砸合法聚合数据）。 |

> **外部 / Phase-A 依赖（多数已 de-risk）**：**B4 延迟 ✅ 实测**（phi inline p95 **0.22ms** · 全链 <6ms；fork POC 仅确认）——余项＝inline NLP 覆盖取舍（推荐 **Option B**：regex+异步+L3 默认敏感，见 [02 §10](02-backend-design.md)）· **B5 ✅ 白名单已定 + 契约 v0.7.1 落 admin 代理**（剩 BE-6b 核 fork 字段）· A0 后端建成属 Phase A · **B6 ✅ 已满足**（完全授权 2026-05-31）。签字前：fork POC 确认 B4 + r3 异构复审。

## 结论与处置（authoritative）
- **异构复审状态**：r2 两条 FAIL 根因——**运行态可伪造（B1）已代码闭环 + 测试**；**Console 0-PHI 绕口（H1/B5）读路径设计已改（A0 代理），但 A0 后端属 Phase A 未建**。故**维持 WAIVED**（in-repo 安全 findings 已全 CLOSED）：待 A0 后端 + 外部门禁（B4/B5；**B6 已满足**）+ **r3 异构复审**确认运行态闭环才升签字。
- **B1/B2/B3 → Phase A 代码阻断**：ADR-18 §2/§3 是目标 schema；**v0.5 代码必须改**——model-router **只接受中间件签发的签名 RouteDecision**，拒收任何客户端自报 `data_level/desensitized/lane/map_id/caller_vendor_family`。enforcement 依赖签名机制（须先有中间件）。
- **可现在修（不依赖中间件）**：H2（error sanitize）、H3（收 0-PHI 口径）、M2（RFC 收口）。
- **Phase A 准入升级**（取代 r1 的乐观判断）：
  1. B1 签名 RouteDecision **代码落地 + 集成测试「伪造分级被拒 / 未签 RouteDecision 被拒」**；
  2. H2 / H3 修；
  3. **r3 异构复审**确认运行态闭环（非仅 fixture）→ 才可 WAIVED→签字。
- 本记录 + r1 + 原始 finding 归档 AUDIT_BUNDLE。

> **一句话**：r1 修了**图纸**，r2 指出**实物还能撬**。在签名 RouteDecision 真正落代码、且伪造被集成测试挡住之前，异构闸门保持 **FAIL/WAIVED**。
