# ADR-18 · 网关控制面契约（new-api 内置 Go 中间件 + 签名 RouteDecision）

> **状态**：draft · 待技委 + 合规委会签（**Phase A 准入硬门禁**）
> **触发**：Codex 异构复审 r1 阻断项 B1/B2/B3 + 高项 H1/H2/H3（见 [系统设计复审记录](../system-design/REVIEW-r1-codex.md)）。
> **关联**：RFC r4（锁 new-api）· ADR-11（egress 唯一强制点）· [系统设计 01/02](../system-design/)。
> **一句话**：把「§D.1 顺序」「RouteDecision 不可覆写」从设计叙事**升级为可 enforce 的冻结契约**——分级由网关签发、底座只执行、客户端自报一律不采信。

---

## 1. 决策摘要

1. **gate 编排 = new-api relay 内置 Go 中间件**（进程内，非独立服务）。所有 `/v1/*` 流量**必经**中间件，无旁路。
2. **RouteDecision 冻结为签名结构**（§2）：携 `allowed_model_set[]` / `lane` / `max_data_level` / `map_id`，由中间件 **HMAC 签名**，底座只在集合内扇出，**不得**用客户端 `model_id` 直选渠道。
3. **零信任客户端分级**（§3）：`data_level` / `desensitized` / `lane` **只由中间件在 ①检测 ②脱敏后写入**；PolicyCore **拒收**请求体自报的分级字段。
4. **allowlist 增 `region`/`egress_zone`**（§2.3），PolicyCore 校验 `lane × region`。
5. **new-api 禁用清单**（§5）：关掉一切会绕过 §D.1 的底座能力 + 「deny → provider 0 连接」集成测试。
6. **控制面 HTTP 契约**（§4）：C3–C8 对中间件暴露稳定接口 + 超时/重试/熔断 + fail-closed。

---

## 2. RouteDecision 冻结 schema（取代 02-backend §2.2 的叙事版）

> **现状差距（B2）**：`mcp/model-router/policy.py` 当前 `RouteDecision` 仅 `decision|reason|layer_failed|policy_version|duration_us`，且 `server_v2.py:_build_request` 只裁单个 `model_id`。**Phase A 必须扩 PolicyCore 输出下列字段**，否则不变量②③无法 enforce。

```jsonc
// 中间件签发，底座/缓存/审计全程携带；签名覆盖除 sig 外全字段
{
  "decision_id": "uuid",
  "action": "allow | deny | reroute",
  "reason_code": "ok | unsanitized_l3l4 | not_in_allowlist | role_denied |
                  level_exceeds | heterogeneity | rate_limited",
  "lane": "normal | sensitive",
  "data_level": "L1|L2|L3|L4",            // 中间件判定，非客户端自报
  "max_data_level": "L1|L2|L3|L4",        // 本 set 可承载上限
  "allowed_model_set": ["qwen-max-2026", "deepseek-v4-pro"],  // 底座成本排序仅限此
  "provider_policy": { "region": "境内", "egress_zone": "cn-private",
                       "no_retention": true, "no_training": true },
  "desensitized": true,                    // 仅当 ② 实际产出 map_id 才为 true（M1）
  "map_id": "envelope-id | null",
  "policy_version": "...", "ts": "...",
  "sig": "HMAC-SHA256(key=内部密钥, body=上述全字段)"  // 底座验签后才执行
}
```

- **H1 reroute**：`level_exceeds` 且可降敏时，PolicyCore 返回 `action:reroute` + 重算 `lane:sensitive` 的 `allowed_model_set`，而非单纯 deny。
- **底座契约**：new-api fork 收到 RouteDecision **先验签**；只在 `allowed_model_set` 内按价/延迟/健康排序；retry/fallback 不得越集合；**忽略**请求体里的 `model` 作为选择依据（仅作 set 求交的输入）。

### 2.3 allowlist schema 扩展（H2）
`MODEL_ALLOWLIST.json` 每条增 `region` / `egress_zone`：
```jsonc
{ "id":"claude-sonnet", "vendor_family":"anthropic", "deployment":"public://anthropic",
  "region":"境外", "egress_zone":"overseas-desensitized-only",
  "allowed_agent_roles":["coder"], "allowed_data_levels":["L1","L2"], "rate_limit_qps":3 }
```
PolicyCore 新增**层⑥ lane×region 校验**：`lane==sensitive ⇒ egress_zone ∈ {cn-private}`；境外 `egress_zone` 仅接收**已脱敏** L1/L2，且 `desensitized==true`。

---

## 3. 零信任分级（B3 / M1）

| 字段 | 来源 | 规则 |
|---|---|---|
| `data_level` | **中间件**（基于 ① phi-detector span 结果） | 有 L3/L4 span 未脱敏 → deny；客户端自报一律忽略 |
| `desensitized` | **中间件**（基于 ② desensitize 是否产出 map_id） | 无 span → `false`+L1；有 span → 脱敏成功产 `map_id` 后才 `true` |
| `map_id` | desensitize 输出 | 与密文信封绑定；`desensitized==true` 必须有真实 `map_id` |
| `lane` | PolicyCore | 由 `data_level` + allowlist 推导，非客户端选 |

**不变量**：PolicyCore 接口拒绝请求体中的 `data_level`/`desensitized`/`lane`/`map_id`（若出现即视为攻击 → deny + 审计 `tier_spoof`）。`desensitized:true` 无对应 `map_id` ⇒ 拒。

> 🔴 **现状漏洞（r2 实查 · Phase A 必改）**：v0.5 代码**正相反**——`mcp/model-router/server_v2.py:187/189/195` 把 `desensitized`/`caller_vendor_family`/`data_level` **从客户端 payload 取**，`policy.py:151-153 _has_desensitized_marker` 信任 `metadata["desensitized"]`，`heterogeneity.py:68` 用客户端 `caller_vendor_family`。**Phase A 必做**：① model-router 仅接受携 `sig` 的签名 RouteDecision；② 入口剥离/拒绝一切客户端自报分级字段；③ 集成测试「未签 / 伪造分级 → deny」。见 [REVIEW-r2](../system-design/REVIEW-r2-codecheck.md) B1。

---

## 4. 控制面 HTTP 契约（开放项② · C3–C8 对中间件）

中间件 → 控制面服务，统一 **HTTP/JSON（localhost，Phase B 可评 gRPC）**：

| 服务 | 端点 | 超时 | 失败语义（fail-closed） |
|---|---|---|---|
| phi-detector | `POST /detect` | 内联预算内（rule-first） | 超时/异常 → **deny 或落 sensitive 缓冲**，绝不放行常规 |
| desensitize | `POST /encrypt` | 紧 | 失败 → deny（不得跳脱敏放行） |
| model-router | `POST /evaluate` | 紧 | 失败 → deny |
| injection-scan | `POST /detect` | rule-first 内联，重 NLP 异步 | 内联失败 → deny；异步命中 → 事后告警 + 阻断后续 |
| outbound-safety | `POST /classify` | post-call | 失败 → 缓冲/不回（按 lane） |
| audit-log | `POST /log` | — | **失败 = deny**（见 H5：审计不可用不得放行） |

- inline 仅 rule-first；可选 LLM 分类器（phi 深检 / 注入 / B1）异步或抽样，不进首字节阻塞（守 §G.2）。
- 每服务带**熔断**（默认 5）+ 重试上限；熔断打开 → fail-closed deny。

---

## 5. new-api 底座禁用清单（B1 / H3）

fork 时**移除/硬关**一切绕过 §D.1 的能力（移除优先「禁用开关 + 路由隐藏」，降 rebase 冲突）：

| 禁用 | 原因 |
|---|---|
| 裸 `/api/route`、`/api/audit` 对外暴露 | B1：客户端直调控制面跳过闸门；**仅内网，对外只留 fork `/v1/*`** |
| new-api 内置 cache 在 gate 前命中 | 违反不变量④（缓存只在 gate 后、仅脱敏体） |
| 自动渠道切换/fallback 到 allowlist 外 | 违反不变量③ |
| relay 旁路分支（image/midjourney/video/task 直发） | 必须同样经中间件，否则 §D.1 漏；**逐路径核（待验证）** |
| 请求前 access/provider 日志含原文 | 0-PHI：日志只在脱敏后 |
| 转售面（注册/支付/订阅/兑换/充值/钱包/社交登录） | RFC §F + console §11（合规移除） |

**集成测试（Phase A 验收）**：`deny` 请求 → **provider 0 连接、cache 0 写、上游日志 0 行**；所有 relay 子路由 → 中间件命中率 100%。

---

## 6. 后果

- **正面**：§D.1 五不变量可 enforce；分级不可伪造；底座无自主权；延迟少一跳。
- **代价**：PolicyCore 需扩（Phase A）；fork 维护面增（禁用清单随上游 rebase 复核）；签名密钥需 KMS 托管。
- **Phase A 准入门禁**：本 ADR 会签 + RouteDecision schema 冻结 + 禁用清单集成测试通过 + B4 延迟 POC 达标。

## 7. 替代与否决
- ~~独立 Python 编排器~~：多一跳、且 enforcement 在网关外可被绕过（H6 双轨风险）→ 否决，选内置 Go 中间件。
- ~~信任客户端分级 + 抽查~~：违反 fail-closed，攻击面大 → 否决。
