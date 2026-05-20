---
name: task-decomposition
description: >
  Use this skill at Step 4 of the v2 SOP to decompose an OpenSpec change's
  tasks.md into atomic, prioritized, single-document, ≤2-file-change tasks.
  Enforces strict separation of frontend vs backend tracks, Chinese naming
  for task documents, and explicit dependency order. Each task gets its own
  task document under tasks/, referenced from tasks.md. Chinese trigger
  examples: "任务拆解", "Step 4", "拆任务", "task 拆分", "前后端分离任务".
  Do NOT use before openspec-continue-change finalizes specs, do NOT bundle
  ≥3 files per task. Success = every task ≤ 2 files, every task has its own
  document, ordering reflects priority + dependency, frontend / backend
  tracks are separated.
compatibility: Requires file write under openspec/changes/<slug>/tasks/.
metadata:
  version: "1.0"
  owner: "architect-line"
  category: "spec-helper"
  maturity: "production"
  sop_step: 4
  hard_gate: false
  outputs: "openspec/changes/<slug>/tasks.md (index) + openspec/changes/<slug>/tasks/<chinese-name>.md (per task)"
---

# Task Decomposition

Translates an implementation-ready change into a queue of bite-sized tasks.

## The canonical prompt (verbatim from v1 SOP)

> 将所有任务进行拆分，其中前端与后端任务要分开，每个任务不超过 2 个文件的改动，每个任务单独任务文档，任务按照优先级排序，任务文档名称和文件夹名称尽可能用中文。

## Why these constraints

| Constraint | Why |
|---|---|
| ≤ 2 files | Forces tight blast radius; Agent stays focused; reviews are easy. |
| One doc per task | Audit / trace / parallel review without merge conflicts. |
| Chinese names | Project policy; improves PM legibility. |
| FE/BE separation | Different reviewers; different risk profiles; cleaner deploys. |
| Priority order | First task to clear must unlock the most downstream value. |

## Output structure

```
openspec/changes/<slug>/
├── tasks.md                    # index, ordered list with links + status checkboxes
└── tasks/
    ├── 后端-01-用户匹配引擎雏形.md
    ├── 后端-02-匹配规则配置层.md
    ├── 前端-01-匹配结果展示页.md
    └── ...
```

Each task document:

```markdown
# 后端-01 · 用户匹配引擎雏形

- **状态**: [ ] 未开始 / [x] 已完成
- **优先级**: P0
- **依赖**: -
- **预计文件**:
  - backend/match/engine.py (new)
  - backend/match/__init__.py (edit)
- **Spec 引用**: S1-match-engine
- **验收**: <criteria>
- **风险**: <if any>
```

## Workflow

1. Walk specs/* — derive 1-N tasks per spec.
2. Classify each task as Frontend / Backend / Both (Both is rare; usually splits into two tasks).
3. Estimate files touched — if > 2, split further.
4. Order by P0 → P3.
5. Write per-task documents.
6. Write tasks.md index linking to each.

## Common failure modes

1. **Mega-task with 5 files** — "refactor + add" combo. Mitigation: hard limit, refuse to write a task with > 2 files.
2. **No priority** — "all P0". Mitigation: enforce at most 30% P0 of total.
3. **Cross-track dependency** — frontend task waits on backend task, no annotation. Mitigation: dependencies field is required.
4. **English-only naming** — "task-001-match-engine". Mitigation: project policy is Chinese; apply unless team agrees otherwise.
