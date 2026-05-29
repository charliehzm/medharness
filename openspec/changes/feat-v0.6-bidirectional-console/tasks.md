# Tasks · feat-v0.6-bidirectional-console

> Step 4 产物 · **task group 级**拆解。每个 Codex lane 在阶段 A 把 group 拆成 `T<id>.<M>` leaf（≤ 2 文件/leaf）后提 spec PR 确认，再进阶段 B 实现。
> 标 🔒 = 缝文件 / 共享文件，**单 owner（charliehzm / 我）**，Codex 通过 spec 提需求，不直接改。

---

## Lane 划分

| lane | 负责会话 | task groups | 物理 territory |
|---|---|---|---|
| 缝 | charliehzm / 我 | A0 | `web/src/api/contract/` schema · `openspec/.../specs/A0-*` |
| 后端 | Codex #1 | B1 / B2 / B3 | `mcp/outbound-safety/` · `mcp/rate-limit/` · `mcp/prompt-injection-scan/` |
| 前端 | Codex #2 | F1 / F2 / F3 | `web/`（除 `web/src/api/contract/` 🔒） |

---

## A0 · 只读聚合 API 契约 🔒（缝 · 先冻结）

- [ ] A0.1 契约 schema：定义 6 组只读 GET 端点 + 2 个写口 POST（`/audit/export` 导出、`/config/{section}/propose` 提交审批）的 request/response JSON schema（见 `specs/A0-read-api-contract.spec.md`）
- [ ] A0.2 schema 白名单校验器 + 「api-phi-exfil」red-team drill（返回体 0 PHI 强校验）
- [ ] A0.3 mock server / fixtures：让 FE 在后端 ready 前照契约开工（合成数据）
- **DoD**：契约冻结并打 version tag；mock server 能起；api-phi-exfil drill 通过（0 PHI）

## B1 · 出站输出安全 `mcp/outbound-safety/`（后端）

- [ ] B1.1 出站扫描骨架：接模型响应 → 分类（PHI 回流 / 有害内容 / 幻觉医嘱 / 正常）
- [ ] B1.2 PHI 回流检测：复用 phi-detector 扫响应 → 命中脱敏 / 阻断（0 PHI 原文留存）
- [ ] B1.3 有害内容拦截 + 幻觉医嘱**告警**（不阻断，攒数据）
- [ ] B1.4 事件落 mcp-audit-log（与入站对称）+ 暴露 A0 events 端点所需聚合
- [ ] B1.5 出站合成 corpus + red-team drill：拦截率 ≥ 0.95，p99 ≤ 50ms
- **DoD**：4 类响应分类正确；0 PHI 原文进日志/API；drill 达标

## B2 · 配额限流 / 滥用控制 `mcp/rate-limit/`（后端）

- [ ] B2.1 横切中间件骨架：入站 / 出站均可挂
- [ ] B2.2 维度限流：按上游 + role + 日成本上限
- [ ] B2.3 滥用检测：越权高频 / 刷量 → 限流 + 告警（只看计数/元数据，0 payload）
- [ ] B2.4 暴露 A0 quota 端点所需聚合
- **DoD**：正常流量误伤 ≤ 1%；限流事件落审计；0 PHI

## B3 · RAG 注入隔离加固 `mcp/prompt-injection-scan/`（后端）

- [ ] B3.1 现状评估：当前 1 文件实现的能力边界（写 gap 报告）
- [ ] B3.2 检索内容隔离区分类器：越权指令 / 数据外泄诱导 / 角色劫持 / RAG 检索污染
- [ ] B3.3 隔离区只存**分类标签 + 处置**，不留 payload 原文（防二次传播）
- [ ] B3.4 暴露 A0 security-events 端点所需分类聚合
- **DoD**：阻断率 ≥ 0.99（合成 case）；隔离区 0 payload 原文

## F1 · Console 基座 `web/`（前端 · 先冻结再分视图）

- [ ] F1.1 脚手架：React 18 + TS + Vite + react-router + 轻量状态（无重型 UI 库）
- [ ] F1.2 设计 tokens：从 `prototype/console-demo.html` 抽 navy/teal/violet 色板 + 间距/圆角/阴影
- [ ] F1.3 共享组件库：Card / Badge / Tag / Table / Toast / 状态点 / 进度环 等（对照原型）
- [ ] F1.4 app shell + 路由：侧栏 7 视图 + 顶栏「本页 0 PHI」徽标 + 角色切换
- [ ] F1.5 api-client：照 A0 契约封装，默认连 mock；含合规守卫（禁止把响应写 localStorage）
- [ ] F1.6 样板视图：把「合规·安全态势」从原型迁过来，作为 F2/F3 的结构范本
- **DoD**：基座接口冻结；样板视图跑通（mock 数据）；合规自检（0 PHI in DOM/state/storage/URL）通过

## F2 · 「看」视图 `web/src/views/`（前端）

- [ ] F2.1 流量监控：双向桑基（入站合规 + 出站安全🚧标真实状态）+ 双色事件流 + 筛选
- [ ] F2.2 报表中心：KPI 条 + 报表卡（导出走 A0 导出端点）
- [ ] F2.3 态势页接真数据（样板已在 F1，这里切 mock→真实 + 下钻合规分/安全分）
- **DoD**：三视图照契约渲染；安全事件**只显分类不显 payload**；合规自检通过

## F3 · 「查改」视图 `web/src/views/`（前端）

- [ ] F3.1 审计追溯：血缘图 + 搜索（routing#/阻断#/desens#）+ 详情；导出 AUDIT_BUNDLE 走 A0
- [ ] F3.2 策略配置：左导航分组（合规/安全/治理）+ 面板切换 + diff 预览 + **提交审批（不旁路 Hook）**
- [ ] F3.3 上游接入：列表 + 状态 + 接入向导（只读 + 引导，不直连改配置）
- [ ] F3.4 研发流水线：12 步 SOP 看板（Step 0/10/12 合规闸门标）
- **DoD**：配置变更只产生「提交审批」动作（落审计），**不直接改内核**；审计/反查界面 0 PHI

---

## 依赖图

```
A0 契约（先冻结）
  ├─→ B1 出站安全 ─→ B3 RAG 注入隔离
  ├─→ B2 配额限流（独立，可与 B1 并行起）
  └─→ F1 基座 ─→ F2 看视图
                └─→ F3 查改视图
真数据联调：A0 + 对应 B 端点 ready → FE api-client 切 mock→真实
```

- BE lane 顺序：B1 → B2 →（B1 后）B3；B2 可穿插
- FE lane 顺序：F1 →（冻结后）F2 / F3
- 两 lane 之间靠 A0 契约解耦，**互不阻塞**

## 合并纪律

- 每个 leaf 独立 `feat/T<id>.<M>-<slug>` 分支，base = main，squash
- 并行写、**串行 merge**：一次进一个，另一路 rebase
- 每个 PR 过 maintainer + 异构 Compliance-Agent review（Step 8 + Step 10）
- 🔒 缝文件只由 charliehzm / 我改；Codex 改到会被 review 打回
