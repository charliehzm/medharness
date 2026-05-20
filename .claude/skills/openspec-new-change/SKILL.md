---
name: openspec-new-change
description: >
  Use this skill at Step 3 of the v2 SOP to create the OpenSpec change
  scaffold (proposal.md / design.md / specs/ / tasks.md) for a stage of the
  PRD. Initializes the change directory under openspec/changes/<slug>/, fills
  the proposal with PRD references, and emits a design.md skeleton including
  a Compliance Design section that links to COMPLIANCE_TAG.md. After this
  skill, use openspec-continue-change for full content expansion. Chinese
  trigger examples: "新建 OpenSpec change", "Step 3", "OpenSpec 初始化",
  "建 change", "新建变更". Do NOT use without a signed COMPLIANCE_TAG (Step 0)
  and a clean PRD (Step 1) and aligned TDD (Step 2). Success = change
  directory exists with valid skeleton, all references resolve, no orphan
  spec ids.
compatibility: Requires file write under openspec/changes/. Optional: read PRD / TDD from upstream artifact paths.
metadata:
  version: "1.0"
  owner: "architect-line"
  category: "spec-author"
  maturity: "production"
  sop_step: 3
  hard_gate: false
  outputs: "openspec/changes/<slug>/{proposal.md,design.md,specs/index.md,tasks.md}"
---

# OpenSpec New Change

The bootstrap step of an OpenSpec change. Sets up structure; content fills in the next step (`openspec-continue-change`).

## Scaffolded structure

```
openspec/changes/<slug>/
├── proposal.md                 # 30-second readout: why + scope + stage + DoD
├── design.md                   # technical approach + 合规设计说明
├── specs/
│   └── index.md                # spec id table; one row per shippable behavior
├── tasks.md                    # task list (filled by task-decomposition next)
├── COMPLIANCE_TAG.md           # signed at Step 0 (link or copy)
└── MODEL_ALLOWLIST.json        # active at Step 0
```

## Workflow

1. **Derive slug** — from the PRD stage name (中文允许，URL-safe optional).
2. **Initialize** — create directory + 4 skeleton files.
3. **Fill proposal** — pull from PRD §1, §3, §5 (for the relevant stage).
4. **Fill design** — leave technical body for `openspec-continue-change`; **must** include `## 合规设计说明` section now (data tier, PHI flow, model allowlist summary).
5. **Init specs** — table with at least 1 placeholder row; spec ids of form `S<n>-<short>`.
6. **Init tasks** — empty list; `task-decomposition` fills it.
7. **Sanity** — all references resolve (PRD path, COMPLIANCE_TAG path).

## Compliance Design section template

```markdown
## 合规设计说明

- 数据等级: <L1/L2/L3/L4>（引用 COMPLIANCE_TAG.md §2）
- PHI 流向: <从哪到哪到哪>（如适用）
- 模型 allowlist: <coder/reviewer/architect 选型摘要，详见 MODEL_ALLOWLIST.json>
- 跨境数据: 是 / 否（如是，必须额外说明绕开方式）
- 新增 prompt 注入面: 是 / 否（如是，列出 RAG/工具/外部输入路径）
```

## Common failure modes

1. **Missing COMPLIANCE_TAG link** — design.md 写出来后才发现忘了合规章节。修：本 skill 强制建出该 section。
2. **Slug over-engineering** — `omni-agent-os-stage-3-orchestrator-minimal-execution-v2-redux` 太长。修：保持简短可识别。
3. **Specs without rows** — index.md 留空。修：至少给 1 个占位 spec id。
