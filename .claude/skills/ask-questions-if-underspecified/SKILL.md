---
name: ask-questions-if-underspecified
description: >
  Use this skill when scope ambiguity blocks progress in any SOP step (PRD,
  TDD, design, task decomposition). Produces a tight set of clarifying
  questions (max 5) that, once answered, unblock the next step. Avoids the
  failure mode where Agents proceed on assumption and produce wrong work.
  Chinese trigger examples: "需求不清", "需要澄清", "提问澄清", "范围不明",
  "信息不足要澄清", "ask the user". Do NOT use for exploration (use research),
  do NOT use to delay obvious work. Success = ≤ 5 questions, each
  decision-shaping, each tied to a specific PRD section.
compatibility: No external dependencies. Used by other skills as a sub-step.
metadata:
  version: "1.0"
  owner: "product-line"
  category: "spec-helper"
  maturity: "production"
  sop_step: "1, 2, 3, 4"
  hard_gate: false
  outputs: "clarifying questions list + recommended next action"
---

# Ask Questions If Underspecified

The "stop and clarify" gate. Many AI Coding failures trace back to "Agent assumed X, X was wrong, 4 hours wasted." This skill catches that early.

## Core principle

Only ask **decision-shaping** questions. If the answer changes nothing about what gets built, don't ask.

## Question taxonomy

For each candidate question, classify:

| Type | Ask? | Example |
|---|---|---|
| Decision-shaping | YES | "Should L4 PHI be stored encrypted at rest or only redacted?" |
| Preference | Only if 2 acceptable paths | "Frontend React or Vue?" |
| Trivia | NO | "What color is the button?" (decide and move on) |
| Compliance-touching | ALWAYS | Anything touching tier / model / audit |

## Workflow

1. List unknowns surfaced from the upstream artifact (PRD / TDD / design).
2. Classify each per the taxonomy.
3. Keep at most 5 of type decision-shaping or compliance-touching.
4. Phrase each question so the answer is **bounded** (multiple-choice or numeric).
5. Format with AskUserQuestion tool when available; otherwise inline.
6. **Never** ask "is this OK" / "should I proceed" — those are not clarifications.

## Output

A list of ≤ 5 questions, each with:
- Header (≤ 12 chars chip label)
- Why it matters (one line)
- 2-4 mutually exclusive options (or "numeric input")
- Recommended default

## Common failure modes

1. **Question dump** — asking 15 questions exhausts the user. Cap at 5; everything else is your call.
2. **Open-ended phrasing** — "What do you think about X?" produces non-actionable answers. Always bound.
3. **Asking after committing** — questions came too late, work already started. Run this skill earlier in the SOP.
