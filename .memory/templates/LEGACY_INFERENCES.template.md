# LEGACY_INFERENCES · <project / module>

> Memory artifact · **推断**陈述（基于事实 + 假设）。
> 必须含 `derives_from` 指向具体 LEGACY_FACTS 行 / commit / 文档。
> 区别 LEGACY_FACTS：推断**会随时间过期**（场景变 / 假设错 / 反事实）。

---

## 1. 架构推断

| 推断 | derives_from | 置信度 | 过期条件 |
|---|---|---|---|
| 字段 `patient_name` 设计成 VARCHAR(200) 是为了支持复姓 + middle name | LEGACY_FACTS#L7 + email-2025-09-12 | 中 | 如发现实际只用 50 chars 数据 |
|  |  |  |  |

## 2. 业务推断

| 推断 | derives_from | 置信度 | 过期条件 |
|---|---|---|---|
|  |  |  |  |

## 3. 历史决策推断

| 推断 | derives_from | 置信度 | 过期条件 |
|---|---|---|---|
| v2.0 关闭 Hook 是因为误判率 66% → 实际是产品设计问题不是 Hook 本身 | LEGACY_FACTS + retrospective_2026-03-15 | 高 | — |
|  |  |  |  |

---

## 写作规则

- ✅ 必含 `derives_from`（≥ 1 个 LEGACY_FACTS 引用 / commit / 文档原文路径）
- ✅ 必标"置信度"：高 / 中 / 低
- ✅ 必写"过期条件"：什么情况下本推断作废
- ❌ 不写"无来源推断"（"我觉得"、"应该是"）→ 不上 memory

> **更新频率**：Memory-Curator 周一扫 + change archive 时刷新。
