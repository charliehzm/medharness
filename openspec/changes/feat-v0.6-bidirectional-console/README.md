# Change · feat-v0.6-bidirectional-console

> v0.5.0-edge（入站·开发期·合规）→ **v0.6.0（合规 + 安全双向网关 + 可用 Console）**
> 状态：spec 草拟完成，待三方签字（见 COMPLIANCE_TAG.md §6）

---

## 一句话

补出站方向的安全闸门（输出安全）+ 横切配额限流 + RAG 注入隔离，并把原型落成真正的 React Console；前后端用一套**只读 · 0 PHI** 的聚合 API 契约解耦并行。

## 阅读顺序

1. `proposal.md` — 业务诉求 + 范围 + 成功指标
2. `COMPLIANCE_TAG.md` — Step 0 合规预检（出站 0 PHI + API 出仓边界 + 异构）
3. `design.md` — ADR-12~17（契约先行 / 出站对称 / React 栈 / 前端合规验收）
4. `tasks.md` — task group + lane 划分 + 依赖图
5. `specs/` — A0 契约（缝）/ B1 出站安全 / F1 Console 基座
6. `CODEX_PROMPT.md` — 两个 lane 的 Codex 启动语

## Lane 速查

| lane | 会话 | territory | 起步 |
|---|---|---|---|
| 缝 A0 | charliehzm / 我 | 契约 schema 🔒 | 先冻结 |
| 后端 B1-B3 | Codex #1 | `mcp/outbound-safety/` `mcp/rate-limit/` `mcp/prompt-injection-scan/` | A0 草案后 |
| 前端 F1-F3 | Codex #2 | `web/` | A0 草案后，F1 先冻结 |

## 不可让步

5 红线 + **Console/API/出站全程 0 PHI** + 安全事件不回显 payload + Console 不旁路审批流 + 异构 review + License 永久 Apache 2.0。
