# 调查报告 · 线上 relay 流量未落 `_audit_log`（审计接线缺口）

> 状态：**调查完成 · 待裁决**（不改受保护的 §D.1 gate）
> 触发：接入屏端到端闭环测试（`test_access_closedloop_e2e_live.py`）发现 Console-令牌能打通网关，但该次 relay 在 `_audit_log` 没留行。
> 日期：2026-06-04

---

## 1. 结论（TL;DR）

**线上 relay 流量不产生 `_audit_log` 行。** 审计管道**已建、未接**：审计服务（`mcp/audit-log`）与 model-router 的 `ClickHouseAuditAdapter` 都存在且完整，但 model-router 运行时默认用 `FileAuditAdapter`（写本地 `.audit/routing_log.jsonl`），ClickHouse 适配器从未被注入。因此 Console 看到的审计 / 血缘数据全部来自 `seed_scenarios.py` 灌的**演示数据** + A0 `/audit/export` 的**导出自审计**，没有一条来自真实 relay。

这与 CLAUDE.md 红线 #3「审计全量记录：每次 tool/模型/Skill 调用必须落 `mcp-audit-log`」不符 —— 但因为管道已建、只是默认走 File 适配器，更像是「社区/demo 版先用 seed 演示 Console、生产接线留后」的状态，需维护者确认是**有意的版本边界**还是**待补缺口**。

---

## 2. 证据

| # | 事实 | 来源 |
|---|---|---|
| 1 | 实测：跑多次 live `/v1/chat/completions` 后 `_audit_log` 零新增 relay 行；最新非 `export` 行是 seed（synthetic 时间戳 06:16），而 relay 发生在 ~10:00 | ClickHouse `medharness._audit_log` 直查 |
| 2 | §D.1 gate 调 `phi-detect → desensitize → sign tier → model-router → outbound-safety`，**无任何 audit-log 调用** | `vendor/new-api/middleware/medharness_compliance.go`（grep `audit` 零命中） |
| 3 | `_audit_log` 的两个写入者：① `seed_scenarios.py` 直插（`INSERT INTO _audit_log`，演示数据）；② A0 `/audit/export` → `_append_audit_event`（导出动作的自审计）。**无 live relay 写入者** | `scripts/seed_scenarios.py:244`、`mcp/a0-api/app.py:1730` |
| 4 | model-router 每个 route 决策都调 `audit_adapter.write_routing_decision(record)`（server_v2.py:383/430/516/556/599/643），但 `_RuntimeState.audit_adapter` 默认 = `FileAuditAdapter` → 写 `.audit/routing_log.jsonl`（本地文件，不入 `_audit_log`） | `mcp/model-router/server_v2.py:63,110` |
| 5 | `ClickHouseAuditAdapter`（server_v2.py:123）存在：把 route 决策映射成 T4 审计事件 → 调 audit-log 服务 `append`。但构造要求显式注入 `audit_server`，默认未注入（注释：「v0.5.0 callers should explicitly inject AuditLogServerV2」） | `mcp/model-router/server_v2.py:123-138` |
| 6 | audit-log 服务完整：`append / query / verify / recover / seal_bundle / health / ensure_schema` + hashchain + clickhouse_writer + fallback。建好了，live 无人喂 | `mcp/audit-log/server_v2.py:336-350` |

---

## 3. 审计数据流现状图

```
business → §D.1 gate → [phi → desensitize → sign → model-router → outbound] → upstream
                                          │
                                          └─ router.write_routing_decision(record)
                                                 │
                                                 ▼  (默认适配器)
                                          FileAuditAdapter → .audit/routing_log.jsonl   ← 本地文件 · 死路（不入 _audit_log）

seed_scenarios.py ───────直插────────────────────────────────────────────────→ _audit_log   ← 演示数据
A0 POST /audit/export ── _append_audit_event ───────────────────────────────→ _audit_log   ← 导出自审计

audit-log 服务（append + hashchain + clickhouse_writer + fallback）  ←──── live 无调用者（已建未接）
ClickHouseAuditAdapter（router→T4 事件→audit-log.append）            ←──── 存在但从未注入
```

---

## 4. 方案选项（按风险 / 工作量排序）

### Option A —— 激活 model-router 的 `ClickHouseAuditAdapter`（最低风险 · 不碰 gate · **推荐起步**）
把 `_RuntimeState.audit_adapter` 默认从 `FileAuditAdapter` 换成 `ClickHouseAuditAdapter`（按 env 注入 audit-log 服务客户端）。
- ✅ 每个 route 决策落 `_audit_log`（route 是脊柱核心决策）；**零 Go 改动**；复用已建的适配器 + 服务 + hashchain。
- ⚠️ 只覆盖 model-router 决策（route），不含 phi/desensitize/outbound 各步；需确认 audit-log 服务内网可达 + `ensure_schema` 已建 + 写失败降级（fallback_writer 已有）。
- 工作量：**小**（适配器选择 + 注入 + env 开关 + 回归 + 一条 live 断言）。

### Option B —— §D.1 gate 每请求落一条全链路审计事件（覆盖最全 · 碰受保护 gate）
gate 决策后 POST 一条审计事件到 audit-log 服务（含各步结果 + hashchain）。
- ✅ 全链路单行审计，最贴红线。
- ⚠️ 改**受保护的关键 Go 脊柱**（需维护者会签）；gate 需能到 audit-log（egress allowlist）；必须异步写避免阻塞 relay；写失败策略要定（建议：审计写 fail-open，但 relay 决策本身仍 fail-closed）。
- 工作量：**中-大** + 治理会签。

### Option C —— 各 MCP 自审计（分布式 · 匹配 seed 数据形状）
phi-detector / desensitize / outbound-safety 各自被调时写一条（`action_tool` = 各服务），与 seed 行形状一致（route/scan/encrypt…）。
- ✅ 每步独立留痕，血缘最细。
- ⚠️ 多服务改动 + 一致 hashchain 协调 + 行数放大。
- 工作量：**中-大**。

### Option D —— 确认为社区版边界，文档化
若有意为之：README / 合规清单注明「社区版 Console 审计为演示 seed；生产审计接线（A/B/C）属商业版 / 后续路线」。
- 工作量：**极小**（文档）。

---

## 5. 建议

1. **先 Option A**：激活已建的 `ClickHouseAuditAdapter`（零 Go），拿到真 per-relay route 审计 + hashchain，作为「审计全量记录」的第一步。
2. 若需全链路单行审计，再上 **Option B**（走 gate 维护者会签）。
3. 无论哪条，**先补一条 live 测试**：一次 relay → `_audit_log` 新增一条可按 `context_change_id` 查到的行（`test_access_closedloop_e2e_live.py` 里已预留 change-id hook 位，当时因本缺口未断言）。

---

## 6. 红线 / 风险

- 不改 new-api / QuantumNous 标识（vendor/new-api Rule 5）。
- Option B 碰受保护 gate，需最小化改动 + 维护者会签。
- 审计写失败策略要先定：建议**异步 + 审计写 fail-open**（审计服务挂不阻断 relay），但 relay 合规决策本身仍 **fail-closed**；audit-log 的 `fallback_writer` 已为此设计。
- 先确保 audit-log 内网可达（`medharness_internal`）+ `ensure_schema` 幂等先行。

---

> 本报告只调查不动 gate（按指示）。落地 Option A/B/C 需单独立项。
