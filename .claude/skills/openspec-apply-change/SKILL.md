---
name: openspec-apply-change
description: >
  Use this skill at Step 6 of the v2 SOP to implement one task from the
  change's tasks/ directory at a time. Each invocation should produce a code
  diff for exactly one task document, touching ≤ 2 files, with prompts
  pre-routed through mcp-model-router and any L3/L4 text pre-desensitized
  via phi-desensitize. Updates the task document checkbox upon completion.
  Chinese trigger examples: "执行任务", "OpenSpec apply", "Step 6", "实现
  任务", "应用变更". Do NOT use to implement multiple tasks at once, do NOT
  use without an active MODEL_ALLOWLIST, do NOT use bypassing
  phi-desensitize for L3/L4 text. Success = one task's diff produced, ≤ 2
  files touched, task checkbox flipped, all model calls routed through
  mcp-model-router.
compatibility: Requires file read/write of code + task document. Routes model calls through mcp-model-router.
metadata:
  version: "1.0"
  owner: "coder-line"
  category: "spec-execute"
  maturity: "production"
  sop_step: 6
  hard_gate: false
  outputs: "code diff + updated tasks/<task>.md"
---

# OpenSpec Apply Change

The implementation step. One task per invocation. Stay in scope.

## Discipline

- Read the task document; do exactly what it says.
- Do not bundle unrelated cleanup.
- Do not refactor adjacent code.
- Do not add comments unless WHY is non-obvious.
- If the task is wrong/incomplete, **stop** and route to `prd-implementation-precheck` instead.

## Workflow

1. Open the task document.
2. Read the linked spec(s) for acceptance criteria.
3. If any data-handling code involves L3/L4 → call `phi-desensitize` first; never paste raw values.
4. Plan diff mentally; if > 2 files needed, re-decompose (call `task-decomposition`).
5. Apply changes.
6. Run quick local sanity (type-check, single test).
7. Flip the task document checkbox to `[x]`.
8. Do NOT mark the OpenSpec change as done — that's Step 7 Verify.

## Common failure modes

1. **Scope creep** — "while I'm here, let me also fix..." . Mitigation: discipline; flag adjacent issues to `spawn_task`-style follow-up, not inline.
2. **Bigger diff than spec** — finish the task with 4 files. Mitigation: pause at file 2; re-decompose.
3. **PHI in prompt** — pasted real schema row including patient_id. Mitigation: hook + skill enforcement.
4. **Comments that re-describe code** — adds noise. Mitigation: comments only where WHY is non-obvious.
