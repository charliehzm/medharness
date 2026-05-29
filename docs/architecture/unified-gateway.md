# MedHarness Unified Gateway · 统一合规 + 安全网关架构

> **状态**：v0.6 纲领文档（draft）· 指导从 v0.5.0-edge "AI Coding 体系" 演进为 "LLM 流量合规 + 安全网关"
> **维护**：技术委员会 + 合规委员会
> **关联 ADR**：ADR-01～10（现有内核）+ ADR-11（本文档提出 · egress gateway 闸门下沉）

---

## 1. 背景与定位

### 1.1 为什么要这份文档

v0.5.0-edge 把 MedHarness 做成了一套 **AI Coding 合规体系**：保护开发者用 Claude Code 写代码时不泄漏 PHI。但客户的真实场景是**两个**：

| 场景 | 上游 | 何时 | PHI 风险量级 |
|---|---|---|---|
| **开发期** | Claude Code / Codex / Cursor | 研发期（偶发） | 中 |
| **生产期** | Dify / ComfyUI / 自研业务系统 | 运行时（7×24） | **极高** |

v0.5.0-edge 的闸门强制性**依赖 Claude Code 的 UserPromptSubmit Hook**——这在 Codex 上失效，在 Dify/ComfyUI 上完全不适用（它们不是 IDE）。

且 v0.5.0-edge 只解决**开发期·入站方向·合规**（请求出去前扫 PHI + 路由）。但生产期的流量是**双向**的，且威胁面不止合规：

| 方向 | 威胁类别 | 典型风险 | v0.5.0-edge |
|---|---|---|---|
| 入站（请求→LLM） | 合规 | PHI 裸入 prompt、越权模型 | ✅ 已建内核 |
| 入站（请求→LLM） | 安全 | prompt 注入、调用滥用/刷量 | ⚠️ 注入有内核 · 滥用缺 |
| 出站（LLM→响应） | 安全 | PHI 回流、幻觉医嘱、有害内容 | ❌ 完全未建 |

**核心结论**：真正不可绕的闸门必须 **IDE 无关**，下沉到**网络层**；且必须**双向**（入站扫合规、出站扫安全）。一个统一的 LLM 流量**合规 + 安全网关**，同时服务开发期和生产期。

### 1.2 一句话定位

> 不管是 Claude Code 写代码，还是 Dify 跑生产工作流——只要它调 LLM，**一来一回**的流量就必经同一个 MedHarness Gateway。上游千变万化，合规与安全的强制点只有一个：入站挡 PHI 与注入，出站挡 PHI 回流与有害输出。

---

## 2. 统一架构

```
┌─────────────────────────────────────────────────────────────────┐
│  上游客户端层（谁在调 LLM · 千变万化）                              │
│  开发期: Claude Code │ Codex │ Cursor                            │
│  生产期: Dify │ ComfyUI │ 自研业务系统                            │
│  共同点: 全部通过 base_url 调 LLM API                             │
└──────────────────────────────┬────────────────────────────────┘
                                │ ANTHROPIC_BASE_URL / OPENAI_BASE_URL
                                ↓        → gateway
┌─────────────────────────────────────────────────────────────────┐
│  🛡️ MedHarness Gateway（唯一合规强制点 · 不可绕）                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 协议适配层  OpenAI 兼容 + Anthropic 兼容 + 流式 SSE        │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │ 闸门一 PHI扫描 │ 闸门二 脱敏 │ 闸门三 路由+异构 │ 第四层 注入 │   │
│  │ (phi-detector)│(desensitize)│(model-router) │(inj-scan) │   │
│  ├─────────────────────────────────────────────────────────┤    │
│  │ 审计  全量落 audit-log · 哈希链 WORM · 6 年可重放          │    │
│  └─────────────────────────────────────────────────────────┘    │
│         ↑ 全部复用 v0.5.0-edge MCP 内核 · 只换入口为 HTTP proxy    │
└──────────────────────────────┬────────────────────────────────┘
                                │ 仅放行合规流量
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  下游模型层                                                       │
│  境内私有（DeepSeek/Qwen）  │  境外 API（仅已脱敏 + allowlist 允许）│
└─────────────────────────────────────────────────────────────────┘
  + 网络层 egress firewall：封死直连境外 LLM · 唯一出口 = gateway
```

> **图中闸门为现有 v0.5.0-edge 入站内核**（合规为主 + 注入兜底）。"合规 + 安全网关"完整形态还要补两段，均为 v0.6 增量、尚未建成（🚧）：
>
> | 段 | 方向 | 职责 | 范畴 | 状态 |
> |---|---|---|---|---|
> | 入站闸门一~三 | 请求 → LLM | PHI 扫描 / 脱敏 / 路由 | 合规 | ✅ 现有内核 |
> | 第四层 + 滥用控制 | 请求 → LLM | 注入扫描 + 🚧 配额/限流/刷量 | 安全 | 注入✅ · 滥用🚧 |
> | 🚧 出站输出安全 | LLM → 响应 | PHI 回流扫描 / 有害内容 / 幻觉医嘱拦截 | 安全 | 🚧 v0.6 全新 |
>
> 即：**入站归合规、出站归安全、注入与滥用横切**。出站段与滥用控制是把"合规网关"升级为"合规 + 安全网关"的核心增量。

### 2.1 三层强制（纵深防御）

| 层 | 机制 | 强制力 | 适用场景 |
|---|---|---|---|
| 第 1 层（软·体验） | IDE hook / AGENTS.md 指令 | 弱（可绕） | 仅开发期 · 早提示 |
| **第 2 层（硬·核心）** | **Egress Gateway** | **强（不可绕）** | **开发期 + 生产期** |
| 第 3 层（兜底·事后） | git pre-commit + CI gate | 中（事后） | 仅开发期 |

**第 2 层 gateway 是产品护城河**——其余两层是锦上添花。

---

## 3. 数据流 · 数据怎么到达闸门

核心洞察：**数据不会自己跑到 LLM，一定经过某个动作。我们在每个动作的咽喉点拦截**。

```
开发者 chat 框打字 ─┐
业务代码调 LLM    ─┤
Dify workflow 节点 ─┼─→ 全部通过 base_url ─→ Gateway ─→ 按序过 5 闸门
ComfyUI API 节点  ─┤
RAG 检索结果      ─┘
```

### 3.1 端到端示例（一条 PHI 走完全程）

```
① 上游（Dify RAG 节点 / Codex 代码 / 任意）发起 LLM 请求
   prompt 含 "张三 110101199001011234"   ← PHI

② Gateway 协议适配层归一化 → RouteRequest

③ 闸门一 phi-detector: 扫描命中 PHI
   → context=prod: hard block + 要求脱敏
   → context=dev:   warn + 自动调闸门二

④ 闸门二 desensitize: AES-256-GCM 加密
   → prompt 变 "__NAME_a1__ __ID_b2__"   ← 占位符
   → 反查表落 ClickHouse 受控环境

⑤ 闸门三 model-router: 5 层 PolicyCore
   marker ✅ → allowlist ✅ → role ✅ → data_level ✅ → 异构性 ✅

⑥ 第四层 inj-scan: 检测 prompt 注入（RAG 来源尤其重要）

⑦ 转发下游模型（占位符版）· LLM 返回

⑧ Gateway 受控反查（仅授权）→ 还原占位符

⑨ 全程落 audit-log · 哈希链 · 6 年可重放
```

**设计哲学**：原始 PHI 在第 ④ 步就被加密，之后全程只有占位符流动。LLM 看到的、audit 记的、日志里的，全是占位符。

---

## 4. 配置能力（核心）

配置能力是产品可用性的关键——客户不能为了改个阈值去读源码。设计**三层配置接口 + 分场景策略 + 配置治理**。

### 4.1 三层配置接口（同一份配置 · 三种入口）

| 入口 | 用户 | 用途 |
|---|---|---|
| **YAML / GitOps** | 工程师 | 版本化 · code review · CI 校验 |
| **Console GUI** | 合规官 / CTO | 可视化改 · 不碰 YAML · 实时预览 |
| **REST API** | 自动化 / 集成 | 程序化配置 · 批量管理 |

三者操作的是**同一份配置真相**（Console 改完生成 YAML diff · API 同理）· 避免配置漂移。

### 4.2 配置分层（6 类可配项）

```
gateway-config/
├── upstreams.yaml          # 上游接入（谁能连 gateway）
├── policies.yaml           # 场景策略（dev/prod 松紧）
├── allowlist.yaml          # 模型白名单（复用 MODEL_ALLOWLIST）
├── gates.yaml              # 闸门阈值 + 开关
├── fields.yaml             # PHI 字段定义（复用 31 fields.yml + 客户化）
└── retention.yaml          # 审计 / 备份保留策略
```

#### ① upstreams.yaml · 上游接入

```yaml
upstreams:
  - name: dev-claude-code
    protocol: anthropic           # anthropic | openai
    context: dev                  # 场景标签 → 决定策略松紧
    api_key_ref: secret://dev-cc-key
    rate_limit_qps: 10
  - name: prod-dify-rag
    protocol: openai
    context: prod
    api_key_ref: secret://prod-dify-key
    rate_limit_qps: 200           # 生产高并发
  - name: prod-comfyui-report
    protocol: openai
    context: prod
    api_key_ref: secret://prod-comfyui-key
```

#### ② policies.yaml · 场景策略（dev/prod 松紧分级）

```yaml
policies:
  dev:
    phi_on_hit: warn_and_desensitize    # 开发期: 命中 PHI → 警告+自动脱敏
    data_level_default: L2
    block_on_injection: warn
  prod:
    phi_on_hit: hard_block              # 生产期: 命中 PHI → 硬阻断
    data_level_required: [L3, L4]       # 强制高敏检查
    block_on_injection: block
```

#### ③ gates.yaml · 闸门阈值（每个数字都可调）

```yaml
gates:
  phi_detector:
    enabled: true
    recall_threshold: 0.92            # 红队 gate 阈值
    fp_threshold: 0.15
    context_rules: 6
  model_router:
    heterogeneity_enforce: true       # 异构性强制开关
    circuit_breaker_threshold: 5      # 熔断阈值
    overhead_budget_ms: 5
  injection_scan:
    block_rate_threshold: 0.95
    fp_rate_threshold: 0.10
```

#### ④ fields.yaml · PHI 字段客户化

```yaml
phi_fields:
  inherit: medharness/31-fields       # 继承通用 31 字段
  custom:                             # 客户加自己的字段
    - name: 住院号
      pattern: 'ZY\d{10}'
      data_level: L3
    - name: 医保结算单号
      pattern: '...'
```

### 4.3 配置治理（谁能改 · 怎么审）

配置变更**本身**是合规风险（改松 allowlist = 开后门）· 必须治理：

| 配置类 | 改动权限 | 审批 | 落审计 |
|---|---|---|---|
| upstreams / rate_limit | 技术委员会 | 单签 | ✅ |
| **policies / gates 阈值** | 技术委员会 | **+ 合规委员会会签** | ✅ |
| **allowlist 加模型** | 技术委员会 | **+ 合规委员会会签** | ✅ |
| **fields PHI 字段** | 合规委员会 | 单签 | ✅ |
| retention 缩短保留期 | **双委员会 + 法务** | 三签 | ✅ |

**关键**：每次配置变更落 audit-log（谁 / 何时 / 改了什么 / 谁批的）· 配置也有 6 年可追溯。

### 4.4 配置 UX · 配置中心页面

```
┌────────────────────────────────────────────────────────────────────┐
│ 策略配置                                            [YAML 视图] [保存]│
├────────────────────────────────────────────────────────────────────┤
│ 左侧导航          │  生产环境策略 (context=prod)                      │
│ ┌──────────────┐ │  ┌────────────────────────────────────────┐     │
│ │ ▸ 上游接入    │ │  │ PHI 命中处理                            │     │
│ │ ▾ 场景策略    │ │  │  ○ 仅警告   ● 硬阻断   ○ 警告+脱敏     │     │
│ │   • dev       │ │  │                                        │     │
│ │  ▶ prod ←     │ │  │ 数据分级强制检查                        │     │
│ │ ▸ 模型白名单  │ │  │  ☑ L3   ☑ L4   ☐ L2                    │     │
│ │ ▸ 闸门阈值    │ │  │                                        │     │
│ │ ▸ PHI 字段    │ │  │ 注入防御                                │     │
│ │ ▸ 保留策略    │ │  │  ● 阻断   ○ 警告                        │     │
│ └──────────────┘ │  └────────────────────────────────────────┘     │
│                   │                                                  │
│                   │  ⚠️ 此变更影响 2 个生产上游 (dify / comfyui)      │
│                   │     需合规委员会会签 → [提交审批]                 │
│                   │                                                  │
│                   │  变更预览 (diff):                                │
│                   │   - block_on_injection: warn                    │
│                   │   + block_on_injection: block                   │
└────────────────────────────────────────────────────────────────────┘
```

**配置 UX 三原则**：
1. **改前看影响**："此变更影响 2 个生产上游" → 防误操作
2. **diff 预览**：改了什么一目了然 · 像 code review
3. **嵌入审批流**：高危配置（policies/allowlist）改完不直接生效 · 走会签 → 落审计 · 配置版本可回滚

---

## 5. 可视化设计 / Console UX

> 完整 UX 设计见 [console-ux-design.md](console-ux-design.md)（待补）· 本节聚焦 gateway 相关视图。

### 5.1 信息架构（角色化首屏）

```
MedHarness Console
├── 🏠 合规态势      ← CTO 落点 · 健康分 + 趋势
├── 📊 流量监控      ← gateway 实时流量（开发期 + 生产期分层）
├── 🔍 审计追溯      ← 合规官落点 · 血缘图 + 哈希链 + 监管包
├── 🚦 研发流水线     ← 工程师落点 · change 看板（仅开发期）
├── ⚙️  策略配置      ← 配置中心（§4.4）
└── 📋 报表中心      ← 季度报表 + 监管应对包
```

### 5.2 易用性 5 铁律

| # | 原则 | 落地 |
|---|---|---|
| 1 | 一个数字定生死 | 首屏最大元素 = 合规健康分 0-100 + 红黄绿 |
| 2 | 角色化默认视图 | CTO→态势 / 合规官→审计 / 工程师→流水线 |
| 3 | 渐进披露三层 | 概览→钻取→详情 · 永不一屏塞满 |
| 4 | 零术语门槛 | "PHI recall 1.0" → "患者信息泄漏拦截率 100%" |
| 5 | 每个红灯给出路 | 不只报警 · 直接"点这里看怎么修" + 跳 runbook |

### 5.3 新增核心视图 · 流量监控（gateway 特有）

这是 gateway-first 的杀手锏——**让客户"看见"PHI 被一层层拦下来**。

```
┌────────────────────────────────────────────────────────────────────┐
│ 流量监控                          [全部] 开发期 生产期    实时 ●      │
├────────────────────────────────────────────────────────────────────┤
│  数据流向（PHI 桑基图 · 最近 1 小时）                                │
│                                                                      │
│  上游            闸门                          下游                   │
│  ┌─────────┐                                                         │
│  │Dify RAG │━━━━┓                            ┏━━→ 私有 Qwen (脱敏)   │
│  │ 1.2k/h  │    ┃  ┌──────────────────┐      ┃                       │
│  └─────────┘    ┣━→│ PHI 扫描         │━━━━━━┫                       │
│  ┌─────────┐    ┃  │ 命中 47 → 脱敏   │      ┃                       │
│  │ComfyUI  │━━━━┫  │ 拦截 3 → 阻断 🔴 │      ┗━━→ 境外 (已脱敏 12)   │
│  │ 380/h   │    ┃  └──────────────────┘                              │
│  └─────────┘    ┃                              ✗ 阻断 3（未脱敏 L4）  │
│  ┌─────────┐    ┃                                                    │
│  │Codex dev│━━━━┛                                                    │
│  │ 90/h    │                                                         │
│  └─────────┘                                                         │
│                                                                      │
│  实时事件流                                                          │
│  🟢 14:23:01 dify-rag    L2 脱敏后路由 qwen-max    routing#a1b2      │
│  🔴 14:23:00 comfyui     L4 未脱敏 → 阻断          阻断#c3d4         │
│  🟢 14:22:58 codex-dev   无 PHI 直接路由           routing#e5f6      │
└────────────────────────────────────────────────────────────────────┘
```

**为什么有说服力**：客户能**亲眼看到**自己的 PHI 流量被实时扫描、脱敏、阻断——比任何 PPT 都有力。销售 demo 神器。

### 5.4 上游客户端管理

```
┌────────────────────────────────────────────────────────────────────┐
│ 上游接入                                              [+ 接入新上游]  │
├────────────────────────────────────────────────────────────────────┤
│ 名称              场景   协议       状态    今日流量   PHI 拦截        │
│ ─────────────────────────────────────────────────────────────────  │
│ prod-dify-rag     prod   openai     🟢 健康  8.2k      命中 312/拦 5  │
│ prod-comfyui      prod   openai     🟢 健康  2.1k      命中 88/拦 2   │
│ dev-claude-code   dev    anthropic  🟢 健康  340       命中 12/拦 0   │
│ dev-codex         dev    openai     🟡 限流  890       命中 30/拦 0   │
│                                                                      │
│ [接入新上游] → 选协议 → 选场景(dev/prod) → 生成 base_url + API key   │
│              → 复制配置给 Dify/ComfyUI/IDE                           │
└────────────────────────────────────────────────────────────────────┘
```

**接入向导**：3 步生成上游配置（选协议 → 选场景 → 复制 base_url + key），客户照贴即可——零代码改造。

---

## 6. 分阶段落地

| 阶段 | 范围 | 解决场景 | 新挑战 |
|---|---|---|---|
| **Phase A**（MVP） | OpenAI 协议 proxy + 复用 4 闸门 + 文本 PHI + 基础配置 | Codex / Dify / ComfyUI **文本**工作流 | 协议归一化 + 性能 |
| **Phase B** | Anthropic 协议 + **流式 SSE** + Console 流量监控 + 🚧 **出站输出安全**（PHI 回流/有害内容）+ 🚧 **配额限流**（防滥用刷量） | Claude Code + 生产流式 + 可视化 + 双向防护 | 流式边扫边转发 · 出站低延迟扫描 |
| **Phase C** | 多模态 PHI（影像/DICOM/OCR）+ RAG ingestion 脱敏 + 🚧 **RAG 注入隔离**（外部知识库携带恶意指令）+ 配置治理 | ComfyUI 影像 + Dify 知识库 + 配置审批 | 全新能力 · 最难 |

**Phase A 即覆盖 Codex + Dify + ComfyUI 文本场景**——而文本 LLM 调用是绝大多数医疗 AI 应用主体（RAG 问答 / 病历摘要 / 报告生成）。

---

## 7. 现有资产复用（v0.5.0-edge → gateway）

```
现有（v0.5.0-edge 已完成）              gateway 角色
────────────────────────────           ─────────────────
phi-detector (MCP)          ──复用──→   闸门一内核
desensitize (MCP)           ──复用──→   闸门二内核
model-router PolicyCore     ──复用──→   闸门三内核（核心）
prompt-injection-scan       ──复用──→   第四层内核
audit-log WORM              ──复用──→   审计 + 配置变更追溯
docker-compose + TLS + nginx ─复用──→   gateway 部署（nginx 已是 DMZ 入口！）
MODEL_ALLOWLIST.json        ──复用──→   allowlist.yaml
31 fields.yml               ──复用──→   fields.yaml

新增（gateway 化）:
  + HTTP proxy 入口（OpenAI/Anthropic 协议兼容）  ← Phase A
  + 流式 SSE 支持                                  ← Phase B
  + Console 流量监控 + 配置中心                     ← Phase B
  + 多模态 PHI + RAG ingestion 脱敏                ← Phase C
```

**v0.5.0-edge 90% 是 gateway 内核**——nginx DMZ 入口、5 层 PolicyCore、WORM 审计、TLS、容器化全现成。主要新增是**协议兼容 proxy 入口层**。

---

## 8. 待解 Gap（诚实清单）

| Gap | 类别 | 影响 | 阶段 |
|---|---|---|---|
| 协议归一化（OpenAI + Anthropic 双协议） | 合规/通用 | Phase A 核心 | A |
| 流式 SSE PHI 扫描（边扫边转发） | 合规 | 生产系统大量用 streaming | B |
| 高并发性能（生产 QPS vs 5ms budget） | 通用 | 生产延迟 | B |
| **调用滥用 / 刷量（配额·限流·成本护栏）** | **安全** | **生产被打爆 / 成本失控 / 越权高频调用** | **B** |
| **LLM 输出安全（出站扫 PHI 回流 / 有害内容 / 幻觉医嘱）** | **安全** | **响应把 PHI 带回 / 输出不当医疗建议——出站完全未扫** | **B/C** |
| **多模态 PHI（DICOM/影像/OCR）** | **合规** | **ComfyUI 医学影像扫不到** | **C（最难）** |
| RAG ingestion 脱敏（入库时 vs query 时） | 合规 | Dify 知识库 PHI | C |
| **RAG 注入隔离（外部知识库携带恶意指令）** | **安全** | **检索结果里的隐藏指令劫持模型行为** | **C** |
| 工作流多跳 PHI 一致性（map_id 跨节点） | 合规 | Dify 多 LLM 节点串联 | C |

> **诚实标注**：上表"安全"类三行（调用滥用 / 出站输出安全 / RAG 注入隔离）是把网关从"合规"升级到"合规 + 安全"的新增范畴，均为 🚧 v0.6 未建能力；现有 v0.5.0-edge 仅注入扫描有内核（入站方向）。

---

## 9. ADR-11（本文档提出 · 待正式落 design.md）

**ADR-11 · IDE 无关的 egress gateway 闸门下沉**

- **决策**：闸门强制点从"IDE hook / MCP 调用"下沉到"网络层 egress gateway（OpenAI/Anthropic 协议兼容 HTTP proxy）"· **双向拦截**（入站扫合规、出站扫安全）· 服务开发期（Claude Code/Codex）+ 生产期（Dify/ComfyUI/自研）统一。
- **替代**：A) 继续 IDE hook（Codex/Dify 失效）· B) 每个上游单独适配（N×成本）· C) SDK 侵入（上游要改代码）
- **否决理由**：A 不通用；B 不可维护；C 上游零改造原则。network proxy 是唯一 IDE/平台无关的强制点，且是唯一能在出站方向拦截响应的位置。
- **实施约束**：复用 v0.5.0-edge 全部闸门内核 · nginx DMZ 做 proxy 入口 · egress firewall 封直连 · 配置变更落 audit · dashboard 数据边界（永不显示原始 PHI）· 🚧 新增双向闸门（出站扫 PHI 回流/有害输出）+ 安全防线（注入隔离 + 调用滥用/配额）——均为 v0.6 增量

---

## 10. 一句话总结

> MedHarness Gateway 是一个 LLM 流量**合规 + 安全网关**：开发者用 Claude Code/Codex，业务系统用 Dify/ComfyUI——它们只需把 base_url 指向 gateway，**一来一回**的 LLM 流量就在网络层被自动处理：入站扫 PHI、脱敏、按 allowlist 路由、挡注入；出站扫 PHI 回流与有害输出；全程配额限流防滥用、全量审计可追溯。一套部署，开发期生产期通吃，上游零改造，配置可视化——合规与安全双轮驱动。
