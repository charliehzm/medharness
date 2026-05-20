---
name: prd
description: >
  Use this skill to author or expand a Product Requirements Document for a
  medical-data SaaS change. Drives PRD from business intent to a structured
  artifact that includes stage breakdown, measurable acceptance criteria,
  named dependencies, and a compliance section referencing COMPLIANCE_TAG.md.
  Handles iterative expansion: start lean, fill gaps surfaced by
  prd-implementation-precheck, until blockers/warnings are zero. Chinese
  trigger examples: "写 PRD", "PRD 起草", "补全 PRD", "PRD 分阶段", "PRD
  完善", "需求文档撰写". Do NOT use for technical design (that's design.md /
  OpenSpec), do NOT bypass Step 0 (compliance precheck must come first).
  Success = PRD passes prd-implementation-precheck with zero blockers and
  zero warnings; stage breakdown present; compliance section linked.
compatibility: Requires file write under docs/PRD/ or openspec/changes/<slug>/PRD.md. Optional: read related historical PRDs from .memory/ for consistency.
metadata:
  version: "1.0"
  owner: "product-line"
  category: "spec-author"
  maturity: "production"
  sop_step: "1, 2"
  hard_gate: false
  outputs: "docs/PRD/<change-name>.md or openspec/changes/<slug>/PRD.md"
---

# PRD Author

Companion to `prd-implementation-precheck`. Where precheck finds gaps, this skill fills them.

## Output structure (canonical PRD skeleton)

```
# PRD — <change name>

## 0. 元数据
- change_id, owner (PM), date, version
- 引用 COMPLIANCE_TAG.md 与数据等级

## 1. 背景与目标
- 业务问题（事实 + 痛点）
- 这次要解决什么、为什么现在
- 与既有产品/平台的关系

## 2. 用户与场景
- 主要用户角色 + 角色画像
- 核心场景 1-3 个
- 反例场景（这次不解决）

## 3. 功能范围
- In-scope（细到 feature 级）
- Out-of-scope（显式列出）
- Future scope（不在本 change 但未来要做）

## 4. 验收准则
- 业务侧 KPI（baseline + target + 测量方法）
- 用户侧验证（任务完成率、NPS 等）
- 技术侧（性能、可用性、合规通过率）

## 5. 阶段拆分
- Stage 1: 范围 + DoD + 退出准则
- Stage 2: 范围 + DoD + 退出准则
- Stage 3: ...

## 6. 依赖与协作
- 外部依赖（按团队 + 命名 owner + 截止日期）
- 内部依赖（哪些既有模块要改）

## 7. 风险与对冲
- Top 3 风险 + 对冲

## 8. 合规说明
- 链接 COMPLIANCE_TAG.md
- 数据等级
- 模型 allowlist 摘要
- PHI 流向描述

## 9. 关联文档
- TDD、design.md、相关 prototype
```

## Workflow

1. **Anchor** — 把用户的 business intent 转成第 1-2 章。
2. **Scope** — 第 3 章是 PRD 的灵魂；显式列出 not-doing。
3. **Measurability** — 第 4 章的每个 KPI 必须给"如何测"。
4. **Stage** — 第 5 章按 "shippable stage" 拆分，不按 "month"。
5. **Compliance link** — 第 8 章引用 Step 0 的 COMPLIANCE_TAG，不重复写。
6. **Iterate** — 跑 `prd-implementation-precheck` → 修 blocker/warning → 直到 0/0。

## Common failure modes

1. **抽象目标无 KPI**：写"提升用户体验"而无指标。修：每个目标必须给"上线后我们看哪个数字"。
2. **No-out-of-scope**：只写做什么不写不做什么。修：每个 in-scope 配一条 out-of-scope。
3. **Stage = 时间切片**：错。Stage = 价值切片，每个 stage 上线即有用。
4. **合规章节空填**：写"遵守 HIPAA/PIPL" 而无具体引用。修：必须 link 到 COMPLIANCE_TAG.md 的具体条款。
