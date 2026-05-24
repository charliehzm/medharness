# Proposal · T7 prompt injection drill 4

> Parent change: `feat-edge-tier-production-v0.5.0`
> Parent task group: `T7 · drill 4 prompt injection`
> Parent task list: `../tasks.md`
> Status: spec-only decomposition for maintainer review

## 1. One Sentence

T7 turns drill 4 from a structured stub into a gated prompt-injection red-team drill with a local rule-based detector, synthetic attack corpus, and >= 95% block-rate CI gate.

## 2. Scope

In scope for T7:

- A new prompt-injection detector module under `mcp/prompt-injection-scan/`.
- A pure rule / keyword / context-rule detector contract for v0.5.0-edge.
- A 20+ case synthetic injection corpus.
- Replacement of `tests/red-team-drills/drill_injection.py` stub.
- A `run_all.sh` drill 4 gate enforcing the block-rate threshold.
- A final T7 audit summary and 4-way sign-off.

Out of scope for T7:

- PHI detection, PHI classification, or Presidio recognizer changes.
- LLM-based injection classification or cloud model calls.
- Real jailbreak prompt library ingestion.
- Production RAG pipeline integration.
- Content moderation policy unrelated to prompt-injection behavior.
- UI, dashboard, or alerting work.

## 3. Inputs From T1-T4

T7 can rely on these existing patterns:

- T1 / `mcp/phi-detector/` demonstrates a detector module shape: local runtime, rule layer, context post-processing, CLI/stdin-friendly surfaces, and tests that avoid leaking raw matched text.
- `.claude/skills/prompt-injection-scan/SKILL.md` defines the existing skill boundary: scan RAG retrieval results, tool outputs, external documents, and user text before they reach model context.
- T3.8 drill 2 demonstrates a real red-team drill that emits structured JSON and gates `run_all.sh` on case outcomes.
- T4.9 drill 3 demonstrates a fixture-backed drill replacing a stub and adding a thin `run_all.sh` gate.
- T4.10 records that drill 4 is still a stub and belongs to T7.

T7 must not assume:

- The current `drill_injection.py` has any runtime logic beyond accepting `--out`.
- The prompt-injection skill has executable code.
- A real RAG corpus, external tools, or model calls are available.
- The detector can call an external classifier.

## 4. Reviewer Decisions Already Accepted

- Accept: detector implementation location is a new independent `mcp/prompt-injection-scan/` module.
- Accept: detector algorithm is pure rules, keywords, and context rules; no ML or LLM dependency in v0.5.0-edge.
- Accept: corpus is 100% synthetic templates and must not copy real jailbreak prompt libraries.
- Accept: block-rate calculation is binary per case: `blocked` / `not blocked`.
- Accept: drill 4 gate belongs in `tests/red-team-drills/run_all.sh` and enforces >= 95%.

Potential qualifications to resolve through RFC:

- The module should probably expose one stable high-level API first, even if internally it has multiple detector categories.
- The 95% threshold is accepted as the proposed gate, but T7 should confirm whether fixture size and one allowed false negative make the math awkward.
- Corpus categories should be broad enough to cover multilingual and obfuscated attacks without importing real-world exploit text.

## 5. Proposed T7 Shape

T7 should be split into 5 leaves:

1. prompt-injection detector module
2. synthetic attack corpus with 20+ cases
3. `drill_injection.py` implementation
4. `run_all.sh` drill 4 gate
5. final audit summary + sign-off

## 6. Why This Exists

Prompt injection is the missing behavioral red-team gate after PHI detection, desensitization, router allowlisting, and audit WORM hardening.

Without T7:

- malicious retrieved text can become model instructions,
- tool outputs can smuggle tool-abuse requests,
- user text can attempt role escalation,
- the monthly red-team wrapper still reports drill 4 as a stub,
- and CI does not fail when injection blocking regresses.

T7 makes drill 4 measurable, synthetic, local-only, and enforceable.

## 7. Threat Model

T7 focuses on three primary prompt-injection threat classes:

| Threat | Example shape | Blocking target |
|---|---|---|
| Indirect injection | RAG or document text embeds instructions such as "ignore prior policy" | detector flags and drill blocks |
| Tool abuse | Text asks the model to call shell, exfiltrate secrets, or bypass MCP routing | detector flags and drill blocks |
| Role escalation | Text declares itself system/admin/developer and attempts to override hierarchy | detector flags and drill blocks |

Candidate secondary classes for RFC:

- jailbreak phrasing,
- encoding and homoglyph smuggling,
- markdown / HTML / link smuggling,
- JSON schema escape,
- multilingual mixed Chinese-English attacks,
- benign near-miss cases for false-positive tracking.

T7's DoD target is drill-time block rate >= 95% on expected-block cases. Whether T7 includes expected-allow benign controls is an RFC question.

## 8. Handoff

T7 -> T8 CI cron:

- `run_all.sh` should fail when injection block rate drops below the agreed threshold.
- T8 can schedule this gate in GitHub Actions and publish drill 4 JSON as an artifact.
- T8 can later add automated issue creation for injection gate regression.

T7 -> T13 offline build:

- `mcp/prompt-injection-scan/` must stay stdlib-only unless explicitly approved.
- Corpus fixtures should ship in the offline tarball as synthetic red-team data.
- No external model, network endpoint, or package download should be required to run drill 4.

T7 -> future RAG / tool integration:

- Detector output should be stable enough for future RAG retrieval and tool-output hooks.
- A future integration can quarantine or annotate untrusted chunks before model context assembly.

## 9. RFC Questions

The following questions need maintainer answers before T7.1 starts. They are duplicated in `tasks.md` for tracking.
