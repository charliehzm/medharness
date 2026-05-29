# A0 只读聚合 API 契约 🔒

> **单 owner：charliehzm**（前后端的「缝」）。FE 只 `import`，**不改**；BE 照此实现端点。
> 契约变更走「单 owner 改 + 版本号 bump + 双 lane 通知」。Codex 改到此目录会被 review 打回。

当前版本：`CONTRACT_VERSION = 0.6.0`（见 `version.ts`）

## 这是什么

Console 调用的全部端点的 request / response 类型 + 合成 mock fixtures。
前后端靠它解耦并行：**FE 照 mock 写界面、BE 照类型实现端点，谁也不等谁**。后端 ready 后 api-client 从 mock 切真实 fetch。

## 文件

| 文件 | 作用 |
|---|---|
| `version.ts` | 契约版本号 + `API_BASE` |
| `types.ts` | 全部端点的 TS 类型（缝的本体） |
| `endpoints.ts` | 端点路径 / 方法 / `CONFIG_SECTIONS` / `buildPath()` |
| `mock.ts` | `resolveMock(method, path)` → 合成 fixture（无需起 server） |
| `fixtures/*.json` | 合成数据（0 PHI），同时被 FE 与 `api-phi-exfil` drill 消费 |
| `index.ts` | barrel |

## 端点（6 GET + 2 POST）

| key | 方法 | 路径 | 说明 |
|---|---|---|---|
| posture | GET | `/posture` | 综合 / 合规 / 安全分 + 闸门 + 告警 |
| traffic | GET | `/traffic?window=&ctx=` | 入站合规 + 出站安全（出站 `built:false`） |
| events | GET | `/events?cat=&ctx=&limit=` | 合规事件（带 level）/ 安全事件（带 sec_type，payload 恒 null） |
| audit | GET | `/audit/{ref}` | 血缘（ref 如 `routing#a1b2`），未命中 404 |
| upstreams | GET | `/upstreams` | 上游状态 + 聚合 PHI 摘要 |
| config | GET | `/config/{section}` | 只读策略快照（10 section） |
| auditExport | POST | `/audit/export` | 导出 AUDIT_BUNDLE（**必落审计**） |
| configPropose | POST | `/config/{section}/propose` | 配置变更**唯一写口**（提交审批，不旁路 Hook） |

## 不可让步（ADR-15 / COMPLIANCE_TAG）

- 返回体只允许：占位符（`__NAME_a1__`）/ 哈希（`routing#a1b2`）/ 聚合数与分类标签
- 安全事件 `payload` 字段**恒 null**（不回显，防二次传播）
- **永不**含原始 PHI / 反向映射表
- 错误体 `msg` 不得含系统版本 / 栈 / 内部路径
- 未建能力（outbound / quota）以 `built:false` 标注，前端渲染 🚧

## 冻结校验

```bash
# 返回体 fixtures 0 PHI（强校验）
bash tests/red-team-drills/run_all.sh --only api-phi-exfil
# 期望：phi_hits = [] · payload_violations = [] · passed = true
```

> git tag `contract-v0.6.0` 在本契约合并入 main 后由 maintainer 打（不在 feature 分支打）。
