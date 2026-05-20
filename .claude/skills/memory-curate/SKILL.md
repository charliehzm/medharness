---
name: memory-curate
description: >
  Use this skill on a weekly cadence and at every change archive to keep the
  project's tiered memory (MEMORY.md index + per-topic memory files +
  workspace artifacts under .memory/) coherent and fresh. Detects stale
  entries, merges duplicates, prunes superseded facts, refreshes the
  inference layer from the latest verified facts, and produces a weekly
  curation report. Counteracts the "stale memory commands decisions"
  failure mode that silently degrades long-running AI Coding sessions.
  Chinese trigger examples: "记忆刷新", "memory 整理", "刷新 MEMORY.md",
  "记忆失效检测", "记忆周报", "整理 .memory/". Do NOT use to write new
  factual memory (let domain skills do that), do NOT use as a substitute
  for an actual audit (this is hygiene, not compliance). Success = no
  duplicates remain, every fact has a `last_verified` ≤ 14 days, the
  inference layer matches the fact layer, weekly report saved with
  curation actions logged.
compatibility: Requires read/write of .memory/ tree, optional access to git history (for evidence-of-staleness), optional access to mcp-audit-log (for skill-touched files).
metadata:
  version: "1.0"
  owner: "memory-curator"
  category: "knowledge-hygiene"
  maturity: "production"
  sop_step: "cross-cutting (weekly + on-archive)"
  hard_gate: false
  outputs: ".memory/MEMORY.md (refreshed) + .memory/curation/weekly_<YYYY-MM-DD>.md"
---

# Memory Curate

The least flashy and most consequential skill in the system. Without it, the project's memory layer slowly accumulates stale guidance that misleads every future AI Coding session.

## Core mental model

Memory has **two layers**:

- **Facts** — observations grounded in code / docs / decisions at a specific time
- **Inferences** — derived claims about how things work / what to do

Inferences depend on facts. If a fact changes and inferences don't update, the AI starts giving advice based on a world that no longer exists.

```
Fact   (2026-01): "we use PostgreSQL 13, pgvector ext disabled"
Infer  (2026-01): "for vector search, use a separate Milvus instance"
   ↓
Fact   (2026-04): upgraded to PG 16, pgvector enabled        ← changed
Infer  (2026-01): "use a separate Milvus instance"            ← now stale
   ↓
Without curation: AI keeps suggesting Milvus, even though pgvector is now available
With curation:    inference is invalidated → re-derived → suggests pgvector
```

Your job is to detect and repair these mismatches.

## What this skill produces

1. Refreshed `.memory/MEMORY.md` (the index)
2. Updated individual memory files (with bumped `last_verified` where applicable)
3. `.memory/curation/weekly_<YYYY-MM-DD>.md` — the curation report

## When NOT to use this skill

Skip for:
- Writing new factual content (that's the producing skill's job — `prd-author`, `openspec-apply-change`, etc.)
- Audit/compliance freezing (use `audit-snapshot`)
- Project setup (no memory yet to curate)

## Active context bundle

**Always load first**
1. This `SKILL.md`
2. `.memory/MEMORY.md` — the index itself
3. `reference/staleness-detection.md` — rules for marking entries stale
4. `reference/merge-protocol.md` — how to merge duplicates without losing nuance

**Load on demand**
- `reference/inference-rederivation.md` — when a fact change invalidates an inference
- `reference/git-evidence-protocol.md` — when using git log as staleness signal
- All individual `.memory/*.md` files referenced from MEMORY.md (lazy load per topic)

## Workflow

### Phase 1 · Index audit
- Parse `.memory/MEMORY.md` — does every line resolve to an existing file?
- Find files in `.memory/*.md` not indexed → either index them or recommend deletion
- Find indexed entries with broken paths → fix or remove
- Find duplicate entries (same target, different one-liner) → mark for merge

### Phase 2 · Per-file freshness check
For each memory file, look at frontmatter:
- `last_verified` field present?
- `last_verified` ≤ 14 days?
- File contents reference any code paths / function names / commit hashes that no longer exist (grep + git log check)?

Bucket each file into:
- **Fresh** (verified ≤ 14 days, evidence still exists) — no action
- **Stale-time** (verified > 14 days, evidence still exists) — bump verification or rewrite
- **Stale-evidence** (verified recent, but referenced artifact gone) — flag for owner review
- **Conflict** (two files disagree on the same fact) — flag for merge

### Phase 3 · Fact / inference reconciliation
Walk fact memory files and inference memory files:
- For each inference, find the facts it depends on (declared in frontmatter `derives_from:` or inline `[ref: FACT_X]`)
- If any source fact has changed (different `version`, different `last_verified` content hash) → mark inference **needs-rederive**
- For each needs-rederive inference, attempt automatic re-derivation by re-reading current facts; if non-trivial, leave a TODO for human owner

### Phase 4 · Merge duplicates
For each pair flagged in Phase 1:
- Read both files
- Identify the more-recent / more-detailed version
- Merge into the survivor (preserve unique nuance from both)
- Replace the redundant entry with a `MOVED_TO: <survivor_path>` stub
- Update MEMORY.md to point at the survivor

Per `reference/merge-protocol.md`, never silently delete a fact — always trace it.

### Phase 5 · Prune superseded
For files with frontmatter `superseded_by: <path>`:
- Verify the successor exists and is fresh
- Move the superseded file to `.memory/archive/<YYYY-MM>/` (don't delete; audit may need it)
- Update MEMORY.md

### Phase 6 · Report
Write `.memory/curation/weekly_<YYYY-MM-DD>.md`:
```
# Memory Curation Report — <date>
## Inventory: <N> files, <M> indexed, <K> orphans
## Freshness: <F> fresh, <S> stale-time, <E> stale-evidence
## Merges performed: <list>
## Inferences invalidated: <list with reason>
## Owner action required: <list with @owner + due>
## Health score: <0.0-1.0> (= fresh / total)
```

Submit to Memory-Curator owner + Skill Owner of memory-curate.

## Health score formula

```
health = (count(fresh) + 0.5 * count(stale-time)) / count(total)
target: ≥ 0.95
red:    < 0.85 — escalate to Tech Committee
```

## Hard gate / soft gate

This skill is **soft-gate**: a failing curation report does not block coding. But:
- Health score < 0.85 for 2 consecutive weeks → Tech Committee agenda item
- Stale-evidence count > 0 → owner action within the week
- Inferences needs-rederive > 0 → owner re-derivation before they get cited again

## Common failure modes

1. **Curation = deletion**: skill gets aggressive, deletes "looks unused" memory. Lost institutional knowledge. Mitigation: never delete in Phase 5 — only archive. Recovery is one move command.
2. **Bump-without-read**: skill bumps `last_verified` without reading content. Memory becomes "permanently fresh" by mechanical update. Mitigation: bump requires evidence — either git-log shows the referenced code still exists, or human owner re-acks.
3. **Inference cascade unattended**: one fact change invalidates 12 inferences; skill marks all but no human ever rederives. Mitigation: weekly report tracks inference debt; > 5 outstanding triggers escalation.
4. **Same-topic split**: one memory about "auth flow" sits in two files because two sessions wrote independently. Mitigation: Phase 1 merge detection catches duplicate `topic` frontmatter; Phase 4 merges.
5. **MEMORY.md as a memory itself**: people start writing actual facts into MEMORY.md instead of pointing to a file. Mitigation: enforce MEMORY.md = pointers only (one line per entry, < 150 chars).

## Integration

- **Weekly cron**: invoked by Memory-Curator Sub-agent on Monday morning
- **On-archive**: invoked at end of Step 12 to capture lessons from the just-archived change
- **On-request**: developer can manually invoke when memory feels off

## Output handoff

Returns:
- Path to the weekly report
- Health score
- Outstanding owner actions list
- Suggested next invocation date
