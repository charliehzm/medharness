# LEGACY_FACTS · <project / module>

> Memory artifact · 既有代码 / 业务的**事实**陈述（不含推断）。
> 区别 LEGACY_INFERENCES：事实可在 grep / git log / 数据库中**直接确认**。

---

## 1. 代码事实

| 事实 | 来源 (file:line / commit) |
|---|---|
| 字段 `patient_name` 在 schema 中是 VARCHAR(200) | `db/migrations/0023.sql:12` |
|  |  |

## 2. 业务事实

| 事实 | 来源 (文档 / 邮件 / commit message) |
|---|---|
|  |  |

## 3. 已知 bug / 已知坑（事实陈述）

| bug / 坑 | 来源 |
|---|---|
|  |  |

## 4. 既有合规边界（事实）

| 边界 | 监管来源 / 内部规章 |
|---|---|
|  |  |

---

## 写作规则

- ✅ 写"事实"：可被 grep / git blame / 文档原文复现
- ❌ 不写"推断"："为什么"、"应该"、"可能" → 走 LEGACY_INFERENCES.template.md

> **更新频率**：Memory-Curator 周一扫 staleness（> 14 天未验证 → 标灰）。
