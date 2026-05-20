---
name: requesting-code-review
description: >
  Use this skill at Step 8 of the v2 SOP after Verify passes, to request and
  receive a code review from a Reviewer-Agent (or human reviewer). Packages
  the diff with context (task documents, specs, COMPLIANCE_TAG, design
  rationale), invokes the review, and iterates with systematic-debugging
  until all feedback is closed. Chinese trigger examples: "请求 review",
  "Step 8", "代码审查", "请人 review", "review 这个 change". Do NOT use as
  substitute for Step 10 compliance review, do NOT skip when reviewer
  feedback contains High items. Success = all reviewer feedback closed,
  review thread archived.
compatibility: Requires file read of diff + change context. Reviewer can be Reviewer-Agent (heterogeneous model) or human.
metadata:
  version: "1.0"
  owner: "qa-line"
  category: "spec-helper"
  maturity: "production"
  sop_step: 8
  hard_gate: false
  outputs: "openspec/changes/<slug>/REVIEW_THREAD.md (review packet + responses + close)"
---

# Requesting Code Review

The "second pair of eyes" gate. Functional, not compliance — that's Step 10.

## Review packet contents

When asking for a review, always include:
- The diff (limited to the task's ≤ 2 files)
- The task document
- The relevant spec id(s)
- Reference to design.md and (if applicable) ARCH_INPUT_INDEX
- The PHI handling note (if L3/L4)

## What the reviewer checks

| Layer | Examples |
|---|---|
| Correctness | matches spec; covers acceptance criteria |
| Code health | readable, lean (no dead code, no extra comments) |
| Security | input validation, error handling at boundaries, injection surface |
| Maintainability | tests align, naming sensible |
| Reuse | did the author miss an existing utility (`reference/legacy-utilities-index.md`)? |

## Workflow

1. Compose review packet.
2. Dispatch to Reviewer-Agent (with heterogeneous model — DON'T use coder's model) or to a human.
3. Capture feedback in `REVIEW_THREAD.md`.
4. For each feedback item: classify Critical / Major / Minor.
5. Address Critical + Major via `systematic-debugging`.
6. Minor: address or accept-and-record.
7. Close when all Critical and Major are closed.

## Common failure modes

1. **Self-review on same model** — coder and reviewer share model = correlated blind spots. Mitigation: enforce heterogeneity.
2. **Drive-by approvals** — reviewer skims and approves. Mitigation: require explicit checklist signoff.
3. **Long-running review threads** — drags. Mitigation: 24h SLA; auto-escalate.
