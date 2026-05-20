---
name: quick-fix
description: >
  Use this skill for micro-changes (bugfix / docs / 小配置) that satisfy:
  ≤2 files changed, no L3/L4 PHI field touched, no new LLM call, no spec/design
  modification. This skill routes to the 5-step micro SOP instead of the full
  12-step SOP. Auto-checks via scripts/sop_router.py; if any check fails,
  redirects to full SOP. Chinese trigger examples: "改个小 bug", "修 typo",
  "更新配置", "改一行", "quick fix", "微改动". Do NOT use for feature
  development, multi-stage work, or anything touching patient data /
  model allowlist / spec. Success = sop_router returns "micro" + 5 步流程
  跑完 + MICRO_AUDIT.json 入 mcp-audit-log.
compatibility: Requires scripts/sop_router.py + mcp-audit-log.
metadata:
  version: "1.0"
  owner: "qa-line"
  category: "process-router"
  maturity: "production"
  sop_step: "micro-channel"
  hard_gate: true
  outputs: "MICRO_TAG.md + MICRO_AUDIT.json"
---

# Quick Fix · 微 Change 通道入口

## 核心机制

不是"绕开 SOP"，是**为低风险变更建立第二个并行通道**：

```
用户: "我要修个 typo / fix 个小 bug"
       │
       ▼
   $quick-fix
       │
       ▼
   sop_router 判定 (auto)
       ├─ micro: 5 步流程
       └─ full:  redirect 到完整 SOP
```

## 何时用

- bugfix 改 ≤ 2 文件
- 文档 / README / 注释更新
- 配置 / 常量调整
- 单元测试补全（不动主代码）

## 何时不用（必须走完整 SOP）

- 任何新 feature
- 任何 spec / design 修改
- 任何接口 / 数据模型变化
- 任何 L3/L4 字段相关代码（即便只读）
- 多文件 refactor
- mcp / .claude/skills/ / governance/runbooks/ 内容修改

## 流程（详见 [研发交付SOP-v2.2-micro.md](../../../研发交付SOP-v2.2-micro.md)）

1. **路由判定**：`scripts/sop_router.py --files <列表>` 必须返回 `micro`
2. **MICRO_TAG**：极简版 COMPLIANCE_TAG（自我声明）
3. **实现**：直接改代码
4. **测试**：相关 testcase 跑一遍
5. **PR + 轻量审计**：直接 PR comment review，归档 MICRO_AUDIT.json

## 防伪 micro

`sop_router.py` 强校验：
- 文件数 ≤ 2
- 不触 L3/L4 字段（grep fields.yml 中字段名）
- 不引入 LLM 调用（grep model-router / 模型 API endpoint）
- 不在 restricted dirs（mcp/ skills/ runbooks/ 等）

任一违反 → 自动 redirect 到 full SOP。

## 月度抽查

- Compliance Officer 月度抽 10% micro-change 事后扫描
- 同模块连续 micro 累计 ≥ 5 → 自动告警（怀疑"micro 累计绕 SOP"）

## 失败模式

1. **滥用 quick-fix**：把 feature 拆成 micro 系列 → sop_router 累计检测拦
2. **声明虚假**：MICRO_TAG 自我声明无 PHI 但实际有 → 月度抽查事后处罚
3. **跳过测试**：micro 不跑 test 直接 PR → CI 拦

## 与其他 Skill 的关系

- `compliance-precheck-micro`（v2.2 alias，Step μ1 用）
- `openspec-apply-change`（Step μ2 用）
- `audit-snapshot-micro`（v2.2 新增，Step μ5 用）
