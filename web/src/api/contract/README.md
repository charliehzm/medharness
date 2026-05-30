# A0 只读聚合 API 契约 🔒

> **单 owner：charliehzm**（前后端的「缝」）。FE 只 `import`，**不改**；BE 照此实现端点。
> 契约变更走「单 owner 改 + 版本号 bump + 双 lane 通知」。Codex 改到此目录会被 review 打回。

当前版本：`CONTRACT_VERSION = 0.6.1`（见 `version.ts`）。0.6.1 为 additive · 非破坏：加运行时 0 PHI 守卫（finding #1）。

## 这是什么

Console 调用的全部端点的 request / response 类型 + 合成 mock fixtures。
前后端靠它解耦并行：**FE 照 mock 写界面、BE 照类型实现端点，谁也不等谁**。后端 ready 后 api-client 从 mock 切真实 fetch。

## 文件

| 文件 | 作用 |
|---|---|
| `version.ts` | 契约版本号 + `API_BASE` |
| `types.ts` | 全部端点的 TS 类型（缝的本体） |
| `endpoints.ts` | 端点路径 / 方法 / `CONFIG_SECTIONS` / `buildPath()` |
| `mock.ts` | `resolveMock(method, path)` → 合成 fixture（每个 ok 响应过 `assertNoPhi`） |
| `sanitize.ts` | 运行时 0 PHI 守卫 `assertNoPhi` + branded `Sanitized<T>`（finding #1） |
| `sanitize.test.ts` | 守卫单测（`node --experimental-strip-types --test`，与 drill 同口径） |
| `fixtures/*.json` | 合成数据（0 PHI），同时被 FE 与 `api-phi-exfil` drill 消费 |
| `index.ts` | barrel |

## 端点（11 GET + 2 POST · v0.7.1）

| key | 方法 | 路径 | 说明 |
|---|---|---|---|
| posture | GET | `/posture` | 综合 / 合规 / 安全分 + 闸门 + 告警 |
| traffic | GET | `/traffic?window=&ctx=` | 入站合规 + 出站安全（出站 `built:false`） |
| events | GET | `/events?cat=&ctx=&limit=` | 合规事件（带 level）/ 安全事件（带 sec_type，payload 恒 null） |
| audit | GET | `/audit/{ref}` | 血缘（ref 如 `routing#a1b2`），未命中 404 |
| upstreams | GET | `/upstreams` | 上游状态 + 聚合 PHI 摘要 |
| cost | GET | `/cost?window=` | 成本 KPI/构成/趋势/省钱建议（聚合·0 PHI · v0.7.0） |
| channels | GET | `/channels` | 渠道比价择优（价/延迟/区域/权重/健康 · v0.7.0） |
| config | GET | `/config/{section}` | 只读策略快照（10 section） |
| adminUsers | GET | `/admin/users` | 管理面用户只读代理（白名单·**禁 email/display_name** · v0.7.1 · B5） |
| adminTokens | GET | `/admin/tokens` | 管理面令牌只读代理（白名单·**禁明文 key** · v0.7.1） |
| adminChannels | GET | `/admin/channels` | 管理面渠道只读代理（白名单·**禁 key/base_url** · v0.7.1） |
| auditExport | POST | `/audit/export` | 导出 AUDIT_BUNDLE（**必落审计**） |
| configPropose | POST | `/config/{section}/propose` | 配置变更**唯一写口**（提交审批，不旁路 Hook） |

## 不可让步（ADR-15 / COMPLIANCE_TAG）

- 返回体只允许：占位符（`__NAME_a1__`）/ 哈希（`routing#a1b2`）/ 聚合数与分类标签
- 安全事件 `payload` 字段**恒 null**（不回显，防二次传播）
- **永不**含原始 PHI / 反向映射表
- 错误体 `msg` 不得含系统版本 / 栈 / 内部路径
- 未建能力（outbound / quota）以 `built:false` 标注，前端渲染 🚧

### 运行时 0 PHI 守卫（finding #1）

> 把「返回体 0 PHI」从注释 / spec / drill 约定，升级为**类型 + 运行时**双保险。

- **类型层** `Sanitized<T>`：没过 `assertNoPhi` 拿不到此品牌；api-client 把响应写入 React state 前必须先过守卫。
- **运行时层** `assertNoPhi(value, where?)`：深度遍历响应，命中 PHI 形状或 `payload != null` 即抛 `PhiLeakError`。
- 守卫自身 0 PHI：错误只报「JSON 路径 + 模式类别」，**绝不**把命中原文放进 message / 日志（防 PHI 经异常二次泄露）。
- 模式与 `tests/red-team-drills/drill_api_phi_exfil.py` 同源（drill 扫 fixtures 落地前、守卫扫运行时响应）。

## 冻结校验

```bash
# 返回体 fixtures 0 PHI（强校验 · 落地前）
bash tests/red-team-drills/run_all.sh --only api-phi-exfil
# 期望：phi_hits = [] · payload_violations = [] · passed = true

# 运行时守卫单测（与 drill 同口径 · 类型擦除直跑）
node --experimental-strip-types --test web/src/api/contract/sanitize.test.ts
```

> git tag `contract-v0.6.0`（初版冻结）/ `contract-v0.6.1`（加守卫）在合并入 main 后由 maintainer 打（不在 feature 分支打）。
