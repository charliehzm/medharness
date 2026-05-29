# Design · feat-v0.6-bidirectional-console

> Step 3 产物 · 关键架构决策（ADR）。leaf 级细节由各 Codex lane 在阶段 A 拆解。

---

## 总览：三件套 + 一条缝

```
          ┌─────────────────────────── Console (React) ───────────────────────────┐
          │  F1 基座(tokens/组件/路由/api-client)  F2 看视图   F3 查改视图           │
          └───────────────────────────────┬───────────────────────────────────────┘
                                           │ HTTP · 只读 · 0 PHI
                              ┌────────────▼────────────┐
                              │  A0 只读聚合 API (BFF)   │  ← 单 owner（我）· schema 白名单
                              └────────────┬────────────┘
            ┌──────────────────────────────┼──────────────────────────────┐
            ▼                ▼              ▼               ▼               ▼
      mcp-audit-log   mcp-model-router  mcp-phi-detector  B1 出站安全   B3 注入隔离
        (现有)            (现有)            (现有)        (新·出站)     (加固)
                                                            ▲
                                                       B2 配额限流（横切·入站+出站）
```

入站归合规（已建）、出站归安全（B1 新建）、注入与滥用横切（B3 加固 / B2 新建）、Console 只读消费（A0 缝 + F 系列）。

---

## ADR-12 · 契约先行（contract-first）解耦前后端

**决策**：先冻结 A0 只读 API 契约（OpenAPI/JSON schema），再两 lane 并行。

**理由**：FE 与 BE 是两个独立 Codex 会话，唯一耦合点是 API。若不先定契约，必然联调时炸 + 互相阻塞。契约冻结后：BE 照契约实现端点、FE 照契约 mock 写界面，谁也不等谁；后端 ready 后 FE 的 api-client 从 mock 切真实。

**约束**：契约是单 owner（我 / charliehzm）文件。任何契约变更走「单 owner 改 + 双 lane 通知 + 版本号 bump」，Codex 不得自行改契约。

## ADR-13 · 出站闸门与入站对称，但只拦不改

**决策**：B1 出站安全做成与入站闸门对称的拦截层——扫模型响应的 PHI 回流 / 有害内容 / 幻觉医嘱，**命中即脱敏或阻断 / 告警**，但 v0.6 **不做自动改写或重生成**。

**理由**：
- 对称性让运维心智模型统一（入站扫请求、出站扫响应）。
- 自动纠正内容风险高、判定不成熟，留 v0.7。
- 幻觉医嘱判定误报率高 → v0.6 **只告警不阻断**，先攒数据。

**0 PHI 约束**：出站扫描命中 PHI 回流 → 脱敏为占位符或阻断；**日志 / API / 前端只记分类与聚合，不留响应原文**。与入站同一条红线。

**延迟对冲**：仅对 L3+ 上下文的响应强扫；可异步预扫 + 整段响应扫（流式 SSE 边扫边转发留 v0.7）。

## ADR-14 · 配额限流是横切层，不绑死方向

**决策**：B2 `mcp/rate-limit/` 做成独立横切中间件，入站 / 出站都能挂；维度 = 上游 + role + 日成本。

**理由**：滥用刷量与成本失控既可能在入站（高频请求）也可能在出站（大响应烧 token）。做成横切层避免在每个闸门里重复实现。

**约束**：限流只看计数 / 元数据 / 成本，**不读 payload**，天然 0 PHI。

## ADR-15 · 只读 API 是新的「出仓边界」，schema 白名单强制

**决策**：A0 的每个端点返回体由显式 schema 白名单定义字段；任何未在白名单的字段不得序列化出去。新增 red-team drill「api-phi-exfil」对所有端点返回体做 PHI 扫描。

**理由**：Console 是第一次把闸门内部数据**呈现给人**。这是过去没有的 PHI 出仓面。靠"小心点"不行，必须 schema 层强制 + 红队回归。

**返回内容边界**：占位符（`__NAME_a1__`）/ 哈希引用（`routing#a1b2`）/ 聚合数 / 事件分类标签。**绝不含**：原始 PHI、安全事件 payload 原文、反向映射表。

## ADR-16 · 前端栈 = React + TS + Vite，零冷门依赖

**决策**：Console 用 React 18 + TypeScript + Vite，路由 react-router，状态用轻量方案（Zustand 或 Context，不引 Redux 全家桶），**不引入重型 UI 组件库**（设计 tokens + 自建组件，从原型抽）。

**理由**：
- React+TS+Vite 是最主流、Codex 最熟、团队最易接手的组合。
- 设计已在 `prototype/console-demo.html` 成型（navy/teal/violet tokens + 组件），抽成 tokens + 组件库即可，无需引 antd/MUI 增加体积与锁定。
- 单 FE Codex 顺序建基座→视图，天然一致，无多会话抢 CSS 问题。

**目录**：新建 `web/`（React app root），`prototype/` 保留作设计基准与对照。

## ADR-17 · 前端合规是验收项，不是事后检查

**决策**：以下前端约束写进 F 系列每个 PR 的合规自检，CI 加静态检查：
- DOM / React state / localStorage / sessionStorage **0 PHI**（只占位符 + 哈希 + 聚合）
- URL / query param **不带任何敏感数据**
- 安全事件视图**只渲染分类与处置，不渲染 payload 原文**
- 错误边界 / 报错信息**不泄露系统版本、栈信息、内部路径**
- 不自动接受 cookie / 条款（Console 是内网工具，无第三方 cookie）

**理由**：前端是最容易无意识泄 PHI 的地方（缓存、URL、报错）。把它做成验收项 + 异构 review 重点，比上线后查更可靠。

---

## 依赖与并行

| task group | 依赖 | lane | 可起步条件 |
|---|---|---|---|
| A0 契约 | — | 我 | 立即 |
| B1 出站安全 | A0 契约（提供 events 端点 schema） | Codex #1 | A0 草案出即可 |
| B2 配额限流 | 独立 | Codex #1 | 立即 |
| B3 RAG 注入隔离 | B1 部分基建 + 现有 injection-scan | Codex #1 | B1 后 |
| F1 基座 | A0 契约（mock 用） | Codex #2 | A0 草案出即可 |
| F2 看视图 | F1 冻结 | Codex #2 | F1 后 |
| F3 查改视图 | F1 冻结 | Codex #2 | F1 后 |
| 真数据联调 | A0 + 对应 B 端点 | 两 lane | 各自 ready 后切 |

并行写、串行 merge；缝文件（契约 / model-router 配置）单 owner。
