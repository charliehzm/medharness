---
name: systematic-debugging
description: >
  Use this skill whenever a test fails, a code review surfaces a defect, or a
  bug is reported, to perform structured root-cause analysis rather than
  trial-and-error patches. Walks symptom → narrow → reproduce → minimal repro
  → root cause → fix → regression test. Outputs a debug log entry that
  feeds into Memory and AUDIT_BUNDLE. Chinese trigger examples: "调试", "找
  bug 根因", "系统化调试", "Bug 定位", "test failure 调试", "review 反馈
  修复". Do NOT use for stylistic feedback (just fix), do NOT use for known
  one-line fixes. Success = root cause identified with evidence, fix
  applied at root cause level, regression test added.
compatibility: Requires read of code + test logs + runtime traces. Optional integration with tracing / profiling tools.
metadata:
  version: "1.0"
  owner: "qa-line"
  category: "execute-helper"
  maturity: "production"
  sop_step: "7, 8, 9, 11"
  hard_gate: false
  outputs: "DEBUG_LOG entry (root cause + fix + regression test ref)"
---

# Systematic Debugging

Stops the "patch the symptom, ship, repeat" anti-pattern.

## The cycle

```
Symptom
  ↓ narrow (which input class / which code path)
Reproducer (smallest input that triggers it)
  ↓ instrument (log / trace / debugger)
Hypothesis (1 falsifiable claim)
  ↓ test the hypothesis directly
Root cause (the WHY behind the WHAT)
  ↓ fix at root (not symptom)
Regression test (locks behavior)
```

## Anti-patterns

| Anti | What it looks like | Cost |
|---|---|---|
| Try-this-try-that | "let me change X and rerun" | hours wasted, no learning |
| Symptom patch | catch + log + return | bug returns elsewhere |
| Print debugging at scale | scattered prints, none removed | noise, audit hits |
| Fix without test | regression returns | infinite loop |

## Workflow

1. Capture the failure clearly (test name + error + line).
2. Narrow input class — what's special about the failing case?
3. Build a minimal reproducer (independent of the test suite).
4. Form ONE hypothesis. Test it. If wrong, revise.
5. Identify root cause; trace back to design / spec / data invariant.
6. Apply fix at root.
7. Add regression test that exercises the minimal reproducer.
8. Write DEBUG_LOG entry: symptom + reproducer + root cause + fix + test ref.

## Integration

- Triggered by: test failure (Step 9), review feedback (Step 8), bug report, compliance gap (Step 10 → Step 11)
- Output: DEBUG_LOG entries inform `memory-curate` (Phase 3 inference rederive) and `audit-snapshot` (prompts/debug_log/)

## Common failure modes

1. **Hypothesis = "it should work"** — not falsifiable. Mitigation: every hypothesis must predict an observable.
2. **Fix without regression test** — the bug will return. Mitigation: discipline; reject the diff otherwise.
3. **Fix at the wrong layer** — patches caller when bug is in callee's invariant. Mitigation: ask "why did the invariant break".
