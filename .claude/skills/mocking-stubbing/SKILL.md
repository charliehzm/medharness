---
name: mocking-stubbing
description: >
  Use this skill at Step 9 of the v2 SOP to run the change's tests against
  the stage-isolated synthetic mock data produced at Step 5. Handles fixture
  loading, mock service stand-up (DB / external APIs / LLM endpoints), runs
  the test pyramid (unit + integration + e2e where applicable), and
  produces a test result report. On failure, hand off to
  systematic-debugging. Chinese trigger examples: "mock 测试", "Step 9",
  "跑测试用 mock", "联调 mock", "存根服务测试". Do NOT use to test against
  production data, do NOT use without verified mock fingerprints. Success
  = all tests green against stage mock, test result XML produced, no real
  service contacted.
compatibility: Requires test runner; mock service stand-up (docker-compose or in-process). LLM mock returns deterministic stub responses.
metadata:
  version: "1.0"
  owner: "qa-line"
  category: "execute-helper"
  maturity: "production"
  sop_step: 9
  hard_gate: true
  outputs: "openspec/changes/<slug>/test_results.xml + TEST_REPORT.md"
---

# Mocking Stubbing

The "tests must pass against synthetic data" gate.

## Mock layers

| Layer | What's mocked | How |
|---|---|---|
| DB | All persistence | sqlite-in-memory or testcontainers + synthetic fixtures |
| External APIs | Hospital HIS / 3rd party | responses library / wiremock |
| LLM | Model calls | deterministic stub via mcp-model-router test mode |
| Time | clocks | freezegun / fake clock |
| Storage | Object store | localstack / minio |

## Discipline

- **No real service contacted during Step 9**. If a test "needs prod", the test is wrong.
- **No real PHI in fixtures** (enforced upstream by `test-data-generation`).
- **Deterministic** — LLM stubs return canned responses; flaky tests are bugs.

## Workflow

1. Load fixtures from `mock/阶段N-*/`.
2. Stand up mock services (script: `scripts/test/up_mocks.sh`).
3. Run test pyramid: unit → integration → e2e.
4. Collect results as JUnit XML.
5. If green → emit TEST_REPORT.md + hand off to Step 10.
6. If red → hand off to `systematic-debugging`.

## Common failure modes

1. **"Just this once" real call** — test reaches real LLM. Mitigation: hooks block production endpoints in test env.
2. **Flaky LLM stub** — random response in stub. Mitigation: deterministic by seed.
3. **Fixture drift** — fixtures stale vs schema. Mitigation: schema-driven generation.
4. **Mock leak** — test uses real env var. Mitigation: explicit env clear before each test.
