# Proposal · feat-v0.6-bidirectional-console

> Step 1-3 产物。
> 提案日期：2026-05-29
> 提案人：charliehzm
> 状态：待 Compliance Officer + 技术 Lead + 异构 Compliance-Agent 签字
> 关联：v0.5.0-edge proposal §8 已把「Web UI / Dashboard」明确留待 v0.6.0

---

## 1. 业务诉求

v0.5.0-edge 把**入站·开发期·合规**做扎实了（4 闸门真实现 + 离线包）。但客户进入生产 PoC 后暴露两个缺口：

1. **流量是双向的，威胁面不止合规**：v0.5.0 只扫入站请求；模型**响应**回来没人扫——PHI 可能被模型带回（PHI 回流）、可能输出有害内容或幻觉医嘱。生产网关必须双向。
2. **没有控制台，合规价值看不见**：CTO / 合规官 / 工程师只能看日志和 YAML。监管来了要 4 小时交审计包，靠命令行翻 ClickHouse 不现实。合规能力必须**可视化、可操作、可交审**。

PoC 客户的原话需求：「让我领导一眼看懂我们到底合不合规」「出站能不能也挡一下」。

## 2. 我们建议做

把项目推到 **v0.6.0**，定位升级为「**合规 + 安全双向网关 + 可用 Console**」：

- **后端**：补出站方向的安全闸门（输出安全）+ 横切的配额限流 + RAG 注入隔离加固
- **前端**：把 `prototype/console-demo.html` 的设计落成真正的 React Console，接现有 4 闸门的只读数据
- **缝**：一套**只读 · 0 PHI** 的聚合 API 契约，前后端照它解耦并行

## 3. 范围内（必做）

### 后端 lane（Codex #1 · `mcp/`）
- **B1 出站输出安全** `mcp/outbound-safety/`：扫模型响应 → PHI 回流拦截 / 有害内容拦截 / 幻觉医嘱告警；与入站闸门对称，仅记录分类与聚合，0 PHI 原文
- **B2 配额限流 / 滥用控制** `mcp/rate-limit/`：按上游 / role 限流 + 日成本护栏；防刷量与越权高频调用
- **B3 RAG 注入隔离** 加固 `mcp/prompt-injection-scan/`：检索内容隔离区分类器（当前仅 1 文件，偏薄）

### 缝（charliehzm / 我 · 单 owner）
- **A0 只读聚合 API 契约**：Console 调的所有读端点（态势分 / 流量聚合 / 事件流 / 审计血缘 / 路由决策 / 上游状态）。**永不返回原始 PHI**，只给占位符 / 哈希 / 聚合数

### 前端 lane（Codex #2 · `web/`）
- **F1 Console 基座**：React + TS + Vite 脚手架 + 从原型抽的设计 tokens + 组件库 + 路由 + API client（先 mock 契约）
- **F2 「看」视图**：合规·安全态势 / 流量监控（双向桑基 + 双色事件流）/ 报表中心
- **F3 「查改」视图**：审计追溯（血缘 + 搜索）/ 策略配置（面板 + diff）/ 上游接入 / 研发流水线看板

## 4. 范围外（明确告知，避免误期望）

- ❌ 出站段的**自动改写 / 重生成**（v0.6 只做拦截 + 告警，不做内容纠正）
- ❌ 多模态 / DICOM 影像内 PHI 检测（留 v0.7）
- ❌ 流式 SSE 边扫边转发（出站当前按整段响应扫，流式留 v0.7）
- ❌ Console 的写操作直连内核改配置（v0.6 配置变更仍走 PR + 审批流，Console 只做**预览 diff + 提交审批**，不旁路 Hook）
- ❌ Console 多租户 / 账号体系（沿用 edge tier「一家一部署」）
- ❌ 真实 PHI 反查界面（反查永远在受控环境，不进 Console）

## 5. 不可让步的边界

- 5 红线（R1-R5，见 CLAUDE.md）任一不让
- **Console 与只读 API 全程 0 PHI**：界面、DOM、state、localStorage、URL 参数、日志均不得出现原始 PHI；只显示占位符 / 哈希 / 聚合数
- **安全事件不回显 payload 原文**（注入 / 有害内容只记分类与处置，防二次传播）
- **出站段 0 PHI**：扫描模型响应时命中 PHI 即脱敏 / 阻断，不留存原文
- Compliance-Agent 与 Coder 异构性强制（Codex=openai → review/compliance=anthropic/deepseek/qwen）
- License 永久 Apache 2.0 / CC BY-SA 4.0

## 6. 衡量成功

| 指标 | 目标 |
|---|---|
| 出站 PHI 回流拦截率（合成 corpus） | ≥ 0.95 |
| 出站扫描 p99 延迟 | ≤ 50ms（整段响应） |
| 配额限流误伤率（正常流量） | ≤ 1% |
| RAG 注入隔离阻断率（合成 case） | ≥ 0.99 |
| 只读 API 响应**含原始 PHI 的条数** | **0**（red-team 强校验） |
| Console 首屏可交互（TTI） | ≤ 2s（本地内网） |
| Console 视图与原型设计一致性 | maintainer 走查通过 |
| 4h 审计应对（Console 一键导出 AUDIT_BUNDLE） | 通过 |

## 7. 风险与对冲

| 风险 | 概率 | 对冲 |
|---|---|---|
| 出站扫描拉高生产延迟 | 中 | 异步预扫 + 仅对 L3+ 响应强扫；流式留 v0.7 |
| 幻觉医嘱判定误报高 | 高 | v0.6 只**告警不阻断**，攒数据再定阈值 |
| 前后端契约漂移 → 联调炸 | 中 | A0 契约**先冻结**；契约变更走单 owner + 双 lane 通知 |
| 两个 Codex lane 抢共享文件 | 中 | FE/BE 物理隔离（`web/` vs `mcp/`）；缝文件单 owner |
| React 引入重前端栈，团队接不住 | 中 | 选最主流 React+TS+Vite，无冷门依赖；组件不引重 UI 库 |
| 只读 API 不慎泄 PHI | 低但致命 | 契约层 schema 白名单 + red-team「API PHI 渗透」drill 新增 |

## 8. 不在范围（避免 scope creep）

| 想做但本 change 不做 | 理由 | 留待 |
|---|---|---|
| 出站内容自动纠正 / 重生成 | 风险高、判定不成熟 | v0.7+ |
| 多模态 / DICOM PHI | 需影像模型 | v0.7 |
| 流式 SSE 边扫边转发 | 出站先做整段 | v0.7 |
| Console 直接写内核配置 | 必须保留审批流 | 永不旁路 |
| 托管 SaaS Console | 商业版 | M10+ |

## 9. 决策权 / 签字

| 角色 | 责任 | 签字 |
|---|---|---|
| 提案人 | charliehzm | ✅ 2026-05-29 |
| Compliance Officer | charliehzm（兼任） | ☐ |
| 技术 Lead | charliehzm | ☐ |
| Reviewer / Compliance-Agent（异构） | 独立模型会话 | ☐ |

未签字 → 不进入实现。

## 10. lane 与时间表

```
缝     A0  只读 API 契约（先冻结，gate 后续联调）       ← 我 / charliehzm
后端   B1  出站输出安全  → B2 配额限流 → B3 RAG 注入隔离  ← Codex #1
前端   F1  Console 基座  → F2 看视图   → F3 查改视图       ← Codex #2
```

并行写、串行 merge。FE 在 A0 契约 mock 上开工，不等后端；后端 ready 后 API client 切真实。

## 11. 关联

- 架构纲领：[docs/architecture/unified-gateway.md](../../../docs/architecture/unified-gateway.md)（已升级为合规+安全双向定位）
- 产品设计：[docs/productization/console-product-design.md](../../../docs/productization/console-product-design.md)
- 可点击原型：[prototype/console-demo.html](../../../prototype/console-demo.html)（F 系列视图的设计基准）
- 前置 change：[../feat-edge-tier-production-v0.5.0/](../feat-edge-tier-production-v0.5.0/)

## 12. 后续

三方签字后 → 两个 Codex 会话分别按 `CODEX_PROMPT.md` 的 BE / FE 启动语接手，按 tasks.md 走 12 步 SOP。
