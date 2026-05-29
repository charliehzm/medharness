# 网关底座选型 + 分级条件路由 · 选型/架构 RFC（draft）

> **状态**：draft RFC · 待技术委员会 + 合规委员会会签裁决（**非已决**）
> **关联**：[unified-gateway.md](unified-gateway.md)（ADR-11 已定"egress gateway 是唯一强制点"）· CLAUDE.md 5 红线 + COMPLIANCE_TAG
> **维护**：技委 + 合规委 · **本 RFC 不入 v0.6，是独立定位决策，排期见 §G**
> **修订**：r2（2026-05-29）已纳 PR #107 Codex 异构独立复审（Go-with-changes）三条阻断项 → 见 §E（license）/§D（hook 强制顺序）/§F（fail-closed + egress 硬约束）；遗留产品定位待 maintainer 裁决项见 §G。
> **一句话**：ADR-11 已定"网关是强制点"，但留了两个未决——本 RFC 给建议供技委拍。

---

## 1. 要裁决的两件事

unified-gateway.md §7 把新增工作量定为"**新增 HTTP proxy 协议兼容入口层** + 复用 v0.5 全部闸门内核"。但它没回答：

1. **底座自研还是架在成熟 OSS 上？** 那个"新增 proxy 入口层"——协议归一化、多上游扇出、failover、流式 SSE、计费——是 LiteLLM / one-api 这类项目**已经做得比我们该做的更好**的东西。自己从零写 = 重造轮子，违反"复用不重造"。
2. **小客户"既要合规查得清、又要广便宜"怎么满足？** unified-gateway.md 聚焦"挡 PHI + 按 allowlist 路由"，没展开"干净流量也能享广便宜"这条线。

---

## 2. 主张

> **合规控制面（我们）架在成熟开源网关底座（OSS）之上；按数据分级条件路由——脱敏后的干净流量走"合规受控低成本池（限境内）"，带 PHI 的流量收紧到私有/境内 allowlist。两者同一网关、同一审计链、按敏感度自动分流。**

底座负责"接得广、跑得稳、算得清"；我们只死磕不可替代的那层：**分级路由策略 + PHI 脱敏 + 出入站安全 + 防篡改审计血缘 + 异构治理**。

---

## 3. §A 分层：复用 vs 自研（核心）

| 层 | 最佳 OSS（实时星数 2026-05） | license*（SPDX 已核） | 决策 |
|---|---|---|---|
| 网关底座（协议归一/扇出/failover/计费/SSE） | **one-api** 34k · **LiteLLM** 48.7k · Portkey 11.9k · Higress 8.5k | one-api=**MIT** · LiteLLM=**见注¹** · Portkey=MIT · Higress=Apache | **复用（架在其上）· 候选权衡见 §E** |
| ~~~（同层备选）~~~ ⚠️ **new-api** 36k | — | **AGPL-3.0** | **默认不采用**（network-copyleft 污染 R5 · §E） |
| 成本-质量路由 | RouteLLM 5.0k | Apache | **借鉴/可选评估**：仅在 clean lane 的 `allowed_model_set` 内排序，**无跨 allowlist/跨 lane 选择权**（不得成为第二 policy authority） |
| PHI 检测/脱敏 | **Presidio** 8.4k | MIT | **复用并扩医疗 recognizer**（已是 `phi-detector/recognizers/` 路子） |
| 出入站安全 scan | **LLM Guard** 3.0k | MIT | **借鉴/可选评估**（POC 验 license+数据出仓+延迟+hook 位置达红线后再定）→ B1 出站安全 |
| 注入检测 | rebuff 1.5k / NeMo 6.3k | Apache | 借鉴 → B3 注入隔离 |
| 红队/漏扫 | garak 8.0k · promptfoo 21.7k | Apache / MIT | 复用 → red-team-drills harness |
| 可观测 | Langfuse 28.2k · OpenLLMetry 7.2k | Langfuse=MIT(+**EE**) / OpenLLMetry=Apache | 参考（**非合规级审计**；避开 EE） |
| **分级路由策略（PolicyCore）** | — | — | **自研（护城河）** |
| **防篡改审计 + 血缘（WORM+哈希链+6年）** | — | — | **自研（护城河 · 现有 `audit-log/hashchain.py`）** |
| **异构合规治理 + 0-PHI Console** | — | — | **自研（护城河）** |

\* 上述 SPDX 经 `gh api repos/<r>/license` 核到（2026-05）。**注¹**：`BerriAI/litellm` 仓库 LICENSE GitHub 判为 `NOASSERTION`（非单一干净 SPDX）——SDK 为 MIT，但 `enterprise/` 等目录另有商业许可，**采用前须把版本与"哪些能力在 OSS 核内"钉死**（§E）。license 最终以采用时仓库当前 LICENSE 为准 + **法务复核**。

**判定**：底座 + 脱敏 + 红队该复用；成本路由 / 安全 scan **先 POC 验证再定（降级为可选）**；不可替代的只有「策略 + 审计 + 治理 + 医疗 opinionation」这一层。

---

## 4. §B 架构（在 ADR-11 之上细化"新增 proxy 层"）

```
上游（Claude Code / Codex / Dify / ComfyUI / 自研）  ── base_url ──┐
                                                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ MedHarness Gateway = OSS 底座 + 我们的合规控制面                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ OSS 底座（LiteLLM / one-api）：协议归一 · 扇出 · failover · SSE · 计费 │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ ★ 合规控制面（pre/post-call hook 插进底座）= 我们自研               │  │
│  │   入站: phi-detector → desensitize → model-router(PolicyCore) → inj │  │
│  │     ↳ 产出**结构化、不可被底座覆写**的 routing decision（见 §D）       │  │
│  │   出站: PHI 回流 / 有害 / 幻觉 scan（B1）                           │  │
│  │   全程: audit-log WORM + 哈希链                                     │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────┬──────────────────────────────────┘
        ┌───────────────────────────┴───────────────────────────┐
   clean lane（已脱敏 / L1-L2）                       PHI lane（L3-L4）
   → 合规受控低成本池                                  → 私有 / 境内 allowlist
     （clean-lane provider pool · 限境内 ·              收紧 · 异构强制 · 不出境
      DeepSeek/Qwen/Doubao/Kimi…，仅在
      router 圈定的 allowed_model_set 内排序）
```

底座只做"管子"，**所有合规判断在我们插入的 hook 里**（LiteLLM 有 callback/guardrail 钩子；one-api 需 fork 插 pre/post 钩）。底座**只执行** router 下发的结构化决策（`decision_id / lane / allowed_model_set / provider_policy / audit_labels`），**无自主选模型/跨 lane/跨 allowlist 的权力**——成本排序仅在 `allowed_model_set` 内进行（§D）。

---

## 5. §C 分级条件路由 + SKU（"合规 + 广便宜"的合成）

**脱敏是桥**：脱敏把"贵且受限"的流量转成"便宜且可广发"的流量。

| 流量 | 路由 | 经济性 |
|---|---|---|
| L1-L2 / 已脱敏 / 非临床（常是大头） | clean lane → 合规受控低成本池扇出（限境内）+ allowlist 内成本排序 | 拿到广+便宜红利 |
| L3-L4 / 带 PHI | 收紧 allowlist · 私有/境内 · 异构强制 | 合规优先，贵认了 |

**SKU 两档**：
- **Slim（小厂本地一机）**：OSS 底座 + phi-detector + desensitize + 轻量哈希链审计（用 `audit-log/fallback_writer.py` 替 ClickHouse）+ 合规受控低成本池 + OpenAI 门面。
- **Full**：+ WORM/ClickHouse、出站安全（B1）、注入隔离（B3）、向量库、异构治理。

---

## 6. §D 与现有组件的接法（具体）

| 现有组件 | 接法 |
|---|---|
| `mcp-model-router`（allowlist/heterogeneity/policy） | 作为底座的 **pre-call hook**：在底座**任何外呼/缓存/扇出之前**裁决数据分级 → 决定 clean/PHI lane → 圈定 `allowed_model_set`。下发**结构化、不可被底座覆写**的 decision；底座仅在该集合内做成本排序 |
| `phi-detector`（recognizers/fields.yml） | 建在 **Presidio** 之上扩医疗 recognizer；作入站第一道 hook |
| `desensitize` | 入站第二道 hook；产出占位符版交底座转发；反查表留受控环境 |
| `audit-log`（hashchain/fallback_writer） | **保持自研**（OSS 无合规级 WORM）；底座每次 call 的元数据落审计；slim 档走 fallback_writer |
| 出站安全（B1，进行中） | 借 **LLM Guard** scanner 思路，作底座 **post-call hook** |
| OpenAI 兼容门面（ADR-11） | 由底座原生提供（LiteLLM/one-api 本就 OpenAI 兼容）→ 我们不再自写协议层 |

### §D.1 Hook 强制顺序契约（**阻断项 · 不可让步**）

底座（LiteLLM/one-api）内部本就含 cache / retry / fallback / provider-dispatch / provider-logging 等环节。若合规 hook 接在这些环节**之后**，会出现"PHI 已进缓存/已外呼/已落上游日志"的漏点。故钉死顺序：

```
请求入站
  └─① 合规 pre-call gate（phi-detector → desensitize → model-router → inj-scan）
        │  产出 routing decision（结构化，底座不可覆写）
        ▼  ——— 以下全部发生在 gate 之后 ———
     ② 底座 cache 查询      （命中也不得返回未过 gate 的体）
     ③ 底座 retry / fallback（只在 decision.allowed_model_set 内，不得越权）
     ④ 底座 provider dispatch（实际外呼）
     ⑤ 底座 provider logging（落上游/计费日志）
  └─⑥ 合规 post-call gate（B1 出站 scan）→ 才返回调用方
```

- **deny 的语义**：pre-call gate 判 deny → **不外呼、不写 cache、不落上游日志**，直接合规拒绝 + 审计。
- **缓存只在 gate 之后**：cache key/value 只含**已脱敏**体；命中也必须过 post-call gate 再回。
- **fallback/retry 不越权**：失败重试与降级**只能**在 `decision.allowed_model_set` 内选，**永不**回退到集合外 provider（呼应 §F fail-closed）。
- **可验证**：上述顺序须有集成测试断言（deny→0 provider request、cache 前置门禁、fallback 不越权、audit 在外呼前后均可对账）；列入 §G POC 验收矩阵。
- **接入差异**：LiteLLM 的 callback/guardrail 钩子位置需核是否真在 cache/dispatch **之前**；one-api 需 fork 在请求处理链最前插入——**hook 位置达不到此顺序则该底座不予采用**。

---

## 7. §E license 兼容性（关乎 R5 永久 Apache 2.0 / CC BY-SA 4.0）

> **修正（阻断项 #1）**：上一稿把 `one-api/new-api` 笼统记作 MIT，错。已逐仓 `gh api repos/<r>/license` 复核（2026-05），**逐项拆开**如下。

- **干净兼容（Apache/MIT，可直接组合）**：`one-api`(MIT)、Portkey(MIT)、Higress(Apache)、Presidio(MIT)、LLM Guard(MIT)、garak(Apache)、promptfoo(MIT)、NeMo(Apache)、Guardrails AI(Apache)、RouteLLM(Apache)。
- **⚠️ 默认不采用（network-copyleft，污染 R5 永久 Apache 2.0）**：**`new-api` = AGPL-3.0**。AGPL 的"network use = distribution"条款会要求**对外提供网络服务者公开其修改源码**——与 R5"永久 Apache 2.0"冲突。是否构成义务**取决于部署形态**（见 §G 待裁决：我们 hosted vs 客户本地自部署，责任主体不同），但**默认按最严判：不纳入**；确需评估须**法务专项 + 部署形态钉死**后另议。
- **需核 EE 边界（OSS 核可用，企业目录另有商业许可）**：
  - **LiteLLM**：GitHub LICENSE 判为 `NOASSERTION`（非单一干净 SPDX）——SDK 为 MIT，但 `enterprise/` 等目录另有商业许可。**采用前须把版本 + "哪些能力在 OSS 核内" 钉死**，只用 OSS 核、避开 EE。
  - **Langfuse**：core MIT + EE 商业。仅用 MIT core、避开 EE。
- **底座二选一权衡**：
  - `one-api`（**MIT** · 国产 · 境内厂商全 · 计费现成）→ 最贴小厂"境内广便宜"，**license 最干净**；但需 **fork** 插 pre/post hook（fork 维护成本见 §G）。
  - `LiteLLM`（生态最大 · callback/guardrail 钩子原生）→ hook 接入最省；**须核 NOASSERTION / proxy EE 边界 + 钉版本**。
- **建议**：slim 档优先 `one-api`（license 干净 MIT + 境内池天然契合）；若要最强 hook 生态再评 `LiteLLM` OSS 核（先清 EE 边界）。**`new-api` 默认排除。最终以法务复核为准。**

---

## 8. §F 不做（scope guard · 防止退化成 InferLink）

- **默认拒（fail-closed · 阻断项 #3）**：证明干净才放宽——广发是 gate 放行后的**特权**，不是默认。**任一闸门 fail/超时/不确定**（classifier、router、desensitize、phi-detector 异常或 timeout）→ **默认拒或落 PHI lane，永不滑入 clean lane**。"为保可用而放行"被显式禁止。
- **egress allowlist（呼应 ADR-11）**：底座容器**不得直连任意 provider**；出网经网关 egress allowlist 白名单，集合与 `decision.allowed_model_set` 一致；集合外目标在网络层即被拦（不靠底座自觉）。
- **provider 条款门槛**：clean lane 低成本池的每个 provider 须有 **no-training / no-retention / 私有等价**合同条款 + 境内数据驻留；**无条款者不得入池**。
- PHI lane **永不出境**；clean lane 低成本池**限境内**（去标识≠匿名，跨境仍有 PIPL 残余风险）。
- **缓存默认无原文**：底座 cache / 日志 / telemetry **默认不留原始 prompt/response**；缓存仅允许**脱敏后**体 + 严格 TTL + 租户隔离 + 境内驻留 + 可审计清除。命中缓存也必须过 post-call gate 再回（§D.1）。
- **第三方聚合器非默认入口**：含 InferLink 等聚合器**默认不进** clean lane；确需登记为受控上游须满足 DPA + 境内驻留 + 审计可达 + **置于 router decision 之下**（待 §G 裁决，且须与"clean lane 限境内"一致）。
- **不**做自助注册/充值/发 key（企业受控租户）；**不**为成本跨合规边界选模型；**不**为"保可用"failover 到 allowlist 外。

---

## 9. §G 待技委/合规委裁决

1. 底座：自研 vs 架在 OSS 上？若 OSS → `one-api` vs `LiteLLM`（§E）。`new-api` 默认排除（AGPL）。
2. **部署形态（产品定位 · 直接影响 AGPL/DPA/审计责任主体）**：我们 hosted、客户本地自部署、还是两者都支持？三者对 license 义务、数据驻留责任、审计落点要求不同——**须先定**才能锁 §E/§F。
3. clean lane 是否允许把第三方聚合器（含 InferLink）登记为**受控上游**？若允许，须与 §F"clean lane 限境内 + provider no-retention 条款"一致，并明确是否破例。
4. slim 档审计降级到 `fallback_writer` 哈希链——**合规委单独会签**（不与底座选型捆绑表决）：是否可接受（vs 强制 ClickHouse WORM）。
5. **v0.7 POC 性能预算**：pre-call 串了 phi-detector + desensitize + model-router + inj-scan 后，留给底座 + provider 的 p95/p99 余量是多少？需 maintainer 给目标数。
6. 拟新增 **ADR-18（OSS 底座 + 控制面 hook 化）** + **ADR-19（数据分级条件路由 + 双档 SKU）**（编号顺延，待落 design.md 确认）。
7. 排期：**不入 v0.6**（v0.6 先收 Console + 出站安全 B1）；建议作 v0.7 独立 change，走 12 步 SOP。

### §G.1 POC 验收矩阵（采用任一 OSS 底座前必过）

| 验收项 | 通过判据 |
|---|---|
| pre-call gate 前置 | deny → **0 provider request**、0 cache 写、0 上游日志 |
| 缓存门禁 | cache 命中也过 post-call gate；cache 仅含脱敏体 |
| fallback 不越权 | retry/降级只在 `allowed_model_set` 内，集合外被网络层 + 决策双拦 |
| 审计可对账 | 外呼**前后**均有 audit 记录，哈希链可重放 |
| license 边界 | 实际启用的目录/能力全在 OSS 核（避开 LiteLLM EE / 排除 AGPL） |
| 延迟 | 满足 §G 第 5 项 maintainer 给定的 p95/p99 预算 |

---

## 10. §H 风险与对冲

| 风险 | 对冲 |
|---|---|
| 脱敏召回非 100%，干净流量误放含残留 PHI 出境 | clean lane 限境内 + 出站二次 scan（B1）+ 默认拒 |
| 依赖 OSS 底座 → 供应链/license 风险 | 选 MIT/Apache + 法务复核 + 锁版本 + fork 自持 |
| "广便宜"诱惑稀释 gate | scope guard（§F）写进 ADR + 合规委月度抽查 + fail-closed 默认拒 |
| 底座升级破坏 hook 接口 | hook 接口契约化 + 集成测试 + 锁版本升级窗口 |
| 小客户流量多为 L3/L4 → 便宜红利小 | 老实定位：这类客户价值在"查得清"非"省钱" |
```
