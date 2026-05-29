# 网关底座选型 + 分级条件路由 · 选型/架构 RFC（draft）

> **状态**：draft RFC · 待技术委员会 + 合规委员会会签裁决（**非已决**）
> **关联**：[unified-gateway.md](unified-gateway.md)（ADR-11 已定"egress gateway 是唯一强制点"）· CLAUDE.md 5 红线 + COMPLIANCE_TAG
> **维护**：技委 + 合规委 · **本 RFC 不入 v0.6，是独立定位决策，排期见 §8**
> **一句话**：ADR-11 已定"网关是强制点"，但留了两个未决——本 RFC 给建议供技委拍。

---

## 1. 要裁决的两件事

unified-gateway.md §7 把新增工作量定为"**新增 HTTP proxy 协议兼容入口层** + 复用 v0.5 全部闸门内核"。但它没回答：

1. **底座自研还是架在成熟 OSS 上？** 那个"新增 proxy 入口层"——协议归一化、多上游扇出、failover、流式 SSE、计费——是 LiteLLM / one-api 这类项目**已经做得比我们该做的更好**的东西。自己从零写 = 重造轮子，违反"复用不重造"。
2. **小客户"既要合规查得清、又要广便宜"怎么满足？** unified-gateway.md 聚焦"挡 PHI + 按 allowlist 路由"，没展开"干净流量也能享广便宜"这条线。

---

## 2. 主张

> **合规控制面（我们）架在成熟开源网关底座（OSS）之上；按数据分级条件路由——脱敏后的干净流量走"境内广便宜池"，带 PHI 的流量收紧到私有/境内 allowlist。两者同一网关、同一审计链、按敏感度自动分流。**

底座负责"接得广、跑得稳、算得清"；我们只死磕不可替代的那层：**分级路由策略 + PHI 脱敏 + 出入站安全 + 防篡改审计血缘 + 异构治理**。

---

## 3. §A 分层：复用 vs 自研（核心）

| 层 | 最佳 OSS（实时星数 2026-05） | license* | 决策 |
|---|---|---|---|
| 网关底座（协议归一/扇出/failover/计费/SSE） | **LiteLLM** 48.7k · **one-api/new-api** 34/36k · Portkey 11.9k · Higress 8.5k | MIT / MIT / MIT / Apache | **复用（架在其上）** |
| 成本-质量路由 | RouteLLM 5.0k | Apache | 复用（clean lane 选模型） |
| PHI 检测/脱敏 | **Presidio** 8.4k | MIT | **复用并扩医疗 recognizer**（已是 `phi-detector/recognizers/` 路子） |
| 出入站安全 scan | **LLM Guard** 3.0k | MIT | 借鉴 → 落到 B1 出站安全 |
| 注入检测 | rebuff 1.5k / NeMo 6.3k | Apache | 借鉴 → B3 注入隔离 |
| 红队/漏扫 | garak 8.0k · promptfoo 21.7k | Apache / MIT | 复用 → red-team-drills harness |
| 可观测 | Langfuse 28.2k · OpenLLMetry 7.2k | MIT(+EE) / Apache | 参考（**非合规级审计**） |
| **分级路由策略（PolicyCore）** | — | — | **自研（护城河）** |
| **防篡改审计 + 血缘（WORM+哈希链+6年）** | — | — | **自研（护城河 · 现有 `audit-log/hashchain.py`）** |
| **异构合规治理 + 0-PHI Console** | — | — | **自研（护城河）** |

\* license 以采用时仓库当前 LICENSE 为准，**采用前由法务复核**；见 §6。

**判定**：底座与脱敏/扫描/红队都该复用；不可替代的只有「策略 + 审计 + 治理 + 医疗 opinionation」这一层。

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
│  │   出站: PHI 回流 / 有害 / 幻觉 scan（B1）                           │  │
│  │   全程: audit-log WORM + 哈希链                                     │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────┬──────────────────────────────────┘
        ┌───────────────────────────┴───────────────────────────┐
   clean lane（已脱敏 / L1-L2）                       PHI lane（L3-L4）
   → 境内广便宜池（DeepSeek/Qwen/Doubao/Kimi…        → 私有 / 境内 allowlist
     底座扇出 + RouteLLM 选性价比）                     收紧 · 异构强制 · 不出境
```

底座只做"管子"，**所有合规判断在我们插入的 hook 里**（LiteLLM 有 callback/guardrail 钩子；one-api 需 fork 插 pre/post 钩）。

---

## 5. §C 分级条件路由 + SKU（"合规 + 广便宜"的合成）

**脱敏是桥**：脱敏把"贵且受限"的流量转成"便宜且可广发"的流量。

| 流量 | 路由 | 经济性 |
|---|---|---|
| L1-L2 / 已脱敏 / 非临床（常是大头） | clean lane → 境内广便宜池扇出 + 成本路由 | 拿到广+便宜红利 |
| L3-L4 / 带 PHI | 收紧 allowlist · 私有/境内 · 异构强制 | 合规优先，贵认了 |

**SKU 两档**：
- **Slim（小厂本地一机）**：OSS 底座 + phi-detector + desensitize + 轻量哈希链审计（用 `audit-log/fallback_writer.py` 替 ClickHouse）+ 境内广便宜池 + OpenAI 门面。
- **Full**：+ WORM/ClickHouse、出站安全（B1）、注入隔离（B3）、向量库、异构治理。

---

## 6. §D 与现有组件的接法（具体）

| 现有组件 | 接法 |
|---|---|
| `mcp-model-router`（allowlist/heterogeneity/policy） | 作为底座的 **pre-call hook**：在底座扇出**之前**裁决数据分级 → 决定 clean/PHI lane → 限定 allowlist。clean lane 内才允许底座选性价比 |
| `phi-detector`（recognizers/fields.yml） | 建在 **Presidio** 之上扩医疗 recognizer；作入站第一道 hook |
| `desensitize` | 入站第二道 hook；产出占位符版交底座转发；反查表留受控环境 |
| `audit-log`（hashchain/fallback_writer） | **保持自研**（OSS 无合规级 WORM）；底座每次 call 的元数据落审计；slim 档走 fallback_writer |
| 出站安全（B1，进行中） | 借 **LLM Guard** scanner 思路，作底座 **post-call hook** |
| OpenAI 兼容门面（ADR-11） | 由底座原生提供（LiteLLM/one-api 本就 OpenAI 兼容）→ 我们不再自写协议层 |

---

## 7. §E license 兼容性（关乎 R5 永久 Apache 2.0 / CC BY-SA 4.0）

- **干净兼容（Apache/MIT，可直接组合）**：Portkey、Higress、Presidio、LLM Guard、garak、promptfoo、NeMo、Guardrails AI、RouteLLM。
- **需核边界**：**LiteLLM**（SDK 为 MIT，但 proxy/admin 的企业特性另有商业许可）；**Langfuse**（core MIT + EE 商业）。采用这两者须避开 EE 部分、只用 OSS 核。
- **底座二选一权衡**：
  - `one-api`（MIT · 国产 · 境内厂商全 · 计费现成）→ 最贴小厂"境内广便宜"，**license 最干净**；需 fork 插 hook。
  - `LiteLLM`（生态最大 · callback/guardrail 钩子原生）→ hook 接入最省；**须核 proxy EE 边界**。
- **建议**：slim 档优先 `one-api`（license 干净 + 境内池天然契合）；若要最强 hook 生态再评 `LiteLLM` OSS 核。**最终以法务复核为准**。

---

## 8. §F 不做（scope guard · 防止退化成 InferLink）

- 默认**拒**，证明干净才放宽——广发是 gate 放行后的**特权**，不是默认。
- PHI lane **永不出境**；clean lane 广便宜池**限境内**（去标识≠匿名，跨境仍有 PIPL 残余风险）。
- **不无脑缓存** LLM 响应（医疗缓存是 PHI 地雷）；要做仅缓存脱敏后 + 严格 TTL + 租户隔离。
- **不**做自助注册/充值/发 key（企业受控租户）；**不**为成本跨合规边界选模型；**不**为"保可用"failover 到 allowlist 外。

---

## 9. §G 待技委/合规委裁决

1. 底座：自研 vs 架在 OSS 上？若 OSS → `one-api` vs `LiteLLM`（§7）。
2. clean lane 是否允许把第三方聚合器（含 InferLink）登记为**受控上游**？
3. slim 档审计降级到 `fallback_writer` 哈希链——合规委是否可接受（vs 强制 ClickHouse WORM）？
4. 拟新增 **ADR-18（OSS 底座 + 控制面 hook 化）** + **ADR-19（数据分级条件路由 + 双档 SKU）**（编号顺延，待落 design.md 确认）。
5. 排期：**不入 v0.6**（v0.6 先收 Console + 出站安全 B1）；建议作 v0.7 独立 change，走 12 步 SOP。

---

## 10. §H 风险与对冲

| 风险 | 对冲 |
|---|---|
| 脱敏召回非 100%，干净流量误放含残留 PHI 出境 | clean lane 限境内 + 出站二次 scan（B1）+ 默认拒 |
| 依赖 OSS 底座 → 供应链/license 风险 | 选 MIT/Apache + 法务复核 + 锁版本 + fork 自持 |
| "广便宜"诱惑稀释 gate | scope guard（§8）写进 ADR + 合规委月度抽查 |
| 底座升级破坏 hook 接口 | hook 接口契约化 + 集成测试 + 锁版本升级窗口 |
| 小客户流量多为 L3/L4 → 便宜红利小 | 老实定位：这类客户价值在"查得清"非"省钱" |
```
