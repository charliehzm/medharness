# T1 · phi-detector v3 production · AUDIT_BUNDLE summary

> Change: `feat-edge-tier-production-v0.5.0`
> Task group: `T1 · phi-detector v3 真集成 Presidio`
> Status: production acceptance met for T1 scope
> Date: 2026-05-21
> Scope: verification summary only; no code in T1.9

## 1. Executive Summary

T1 delivered the PHI detector v3 backend needed by MedHarness edge-tier production work.

The implementation moved the detector from stub / rule-only behavior into a Presidio-backed runtime with MedHarness custom Chinese healthcare recognizers, context post-processing, recall drills, synthetic fixtures, and an R4 fingerprint verification CLI.

T1 is now acceptable as the PHI detection backend for T2 desensitization work.

The release gate is satisfied on the synthetic corpus:

- Recall: `1.0` on 220 positive fixture cases / 250 expected PHI mentions.
- Effective recall: `0.95` from detector self-report gate.
- False-positive rate: `0.0909` on 110 negative fixture cases.
- Contract violations: `0`.
- Inference latency: p99 `0.7586 ms` on 1K chars in local CPU regex-only fallback test, below the `100 ms` threshold.
- Fixture fingerprints: stable hashes recorded below.

## 2. PR Ledger

| Leaf | PR | Merge commit | Leaf commit | Summary |
|---|---:|---|---|---|
| T1.1 | [#16](https://github.com/charliehzm/medharness/pull/16) | `f6481d8` | `12dd405` | Added recognizer loader and base CN ID / phone / MRN recognizers. |
| T1.2 | [#18](https://github.com/charliehzm/medharness/pull/18) | `5025daf` | `38d0a90` | Added CN finance, travel, and medical-context recognizers. |
| T1.3 | [#19](https://github.com/charliehzm/medharness/pull/19) | `659150c` | `c7fbcf4` | Added 31-field `fields.yml` schema and strict loader validation. |
| T1.4 | [#20](https://github.com/charliehzm/medharness/pull/20) | `9f81e2f` | `1621e5f` | Added context post-processing, cache contract, and span dedup rules. |
| T1.5 | [#22](https://github.com/charliehzm/medharness/pull/22) | `5fd5815` | `5349589` | Integrated `server_v3.py` with Presidio AnalyzerEngine and response envelope. |
| T1.6 | [#23](https://github.com/charliehzm/medharness/pull/23) | `7ea24ff` | `4b3a29a` | Updated red-team recall drill contract and recall gate enforcement. |
| T1.7 | [#24](https://github.com/charliehzm/medharness/pull/24) | `141081a` | `7e2a47a` | Expanded positive / negative synthetic PHI corpus fixtures. |
| T1.8 | [#25](https://github.com/charliehzm/medharness/pull/25) | `8fc334a` | `aa94666` | Added R4 synthetic fixture fingerprint checker CLI and tests. |

## 3. Delivered Components

### 3.1 Custom CN Recognizers

T1.1 delivered the recognizer loading entry point:

- `mcp/phi-detector/recognizers/__init__.py`
- `mcp/phi-detector/recognizers/cn_core.py`

T1.1 recognizers:

- `CN_ID`
- `CN_PHONE`
- `CN_MRN`

T1.2 delivered finance, travel, and medical-context recognizers:

- `mcp/phi-detector/recognizers/cn_finance_travel.py`
- `mcp/phi-detector/recognizers/cn_medical_context.py`

T1.2 recognizers:

- `CN_BANK`
- `CN_PASSPORT`
- `CN_HK_ID`
- `CN_DRIVERS_LICENSE`
- `CN_ADDRESS`
- `CN_DISEASE_CODE`
- `CN_DRUG_CODE`

### 3.2 Field Contract

T1.3 delivered the field registry:

- `mcp/phi-detector/fields.yml`
- `mcp/phi-detector/recognizers/fields_loader.py`

The field registry contains 31 PHI field definitions.

Each field definition validates:

- `id`
- `presidio_entity`
- `score_min`
- `context_boost.keywords`
- `context_boost.window`

The loader fails closed on malformed schema.

### 3.3 Context Post-Processing

T1.4 delivered:

- `mcp/phi-detector/postprocess.py`
- `tests/test_phi_detector_postprocess.py`

Rules covered:

- Placeholder suppression.
- Log timestamp demotion.
- Name proximity boost / demotion.
- 60-second session cache with LRU max size 10,000.
- CN bank strictness fallback.
- Span dedup, including `CN_DRIVERS_LICENSE` priority over `CN_ID` when context matches.

### 3.4 Presidio Runtime Integration

T1.5 delivered:

- `mcp/phi-detector/server_v3.py`
- `tests/test_phi_detector_server_v3.py`

Runtime contract:

```json
{
  "spans": [
    {
      "start": 0,
      "end": 0,
      "entity_type": "CN_ID",
      "score": 0.95,
      "text_sha256": "<sha256>"
    }
  ],
  "stats": {
    "recall_estimate": 0.95,
    "duration_ms": 0.0
  }
}
```

The response contract does not return raw matched text.

The runtime preserves CLI / stdio compatibility.

The runtime lazy-loads spaCy and falls back to regex-only mode when `zh_core_web_sm` is unavailable.

### 3.5 Recall Drill Contract

T1.6 delivered:

- `tests/red-team-drills/drill_phi_recall.py`
- `tests/red-team-drills/check_recall.py`

The drill now consumes the v3 `spans` envelope.

The drill remains compatible with legacy `hits` during migration.

The gate enforces:

- Recall threshold via `--min`.
- Failed case ids.
- Contract violations.
- Missing / malformed output as exit code `2`.
- Recall history JSON artifact.

### 3.6 Synthetic Corpus

T1.7 delivered:

- `tests/red-team-drills/fixtures/synthetic_phi_corpus.jsonl`
- `tests/red-team-drills/fixtures/synthetic_phi_negative_corpus.jsonl`

Positive corpus:

- 220 rows.
- 250 expected PHI mentions.
- 10 recognizers covered.
- 25 expected mentions per recognizer.
- Source marker: `synthetic`.
- Generator metadata present on every row.

Negative corpus:

- 110 rows.
- 11 categories.
- 10 rows per category.
- Source marker: `synthetic`.
- Generator metadata present on every row.

Negative categories:

- Log timestamp.
- Commit hash.
- UUID.
- Placeholder.
- Code snippet.
- Docs.
- Plain text.
- Medical non-PHI terminology.
- TCM acupoint names.
- Invalid ID / bank values.
- Build artifact MRN-like strings.

### 3.7 Fixture Fingerprint Gate

T1.8 delivered:

- `tools/phi_fingerprint_check.py`
- `tests/test_phi_fingerprint_check.py`

The CLI validates:

- Every JSONL row has `source: "synthetic"`.
- Every JSONL row has generator metadata.
- Row and value hashes are not in the known-real-PHI fingerprint blocklist.
- Row values do not contain forbidden customer markers.
- File-level canonical fingerprints are written to history.

The CLI exit code contract:

- `0`: clean.
- `1`: validation failed.
- `2`: file / parse / history error.

## 4. Final KPI Snapshot

| KPI | Final value | Gate | Status |
|---|---:|---:|---|
| Positive fixture cases | 220 | >= 200 | PASS |
| Positive expected mentions | 250 | >= 200 implied | PASS |
| Recognizer positive coverage | 10 recognizers x 25 mentions | >= 10 each | PASS |
| Recall | 1.0 | >= 0.92 | PASS |
| Effective recall | 0.95 | >= 0.92 | PASS |
| Negative fixture cases | 110 | >= 100 | PASS |
| False-positive cases | 10 | <= 16.5 cases at 15% | PASS |
| False-positive rate | 0.0909 | <= 0.15 | PASS |
| Contract violations | 0 | 0 | PASS |
| `check_recall.py --min 0.92` | pass | pass | PASS |
| p99 inference latency on 1K chars | 0.7586 ms | < 100 ms | PASS |
| Fingerprint checker strict mode | pass | pass | PASS |
| Red-team drill suite | pass | pass | PASS |
| Dryrun e2e CI mode | pass | pass | PASS |

## 5. Fixture Fingerprints

Command:

```bash
python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl --strict
```

Result:

| Fixture | Lines | Fingerprint | Status |
|---|---:|---|---|
| `tests/red-team-drills/fixtures/synthetic_phi_corpus.jsonl` | 220 | `6da2fac1f3c66ab89b0695be89d70c5cf74a874249944b01348b219cc3b862c9` | PASS |
| `tests/red-team-drills/fixtures/synthetic_phi_negative_corpus.jsonl` | 110 | `faa160e6da4e2fa05884e652b4bff2320ec2b28909752a8d172f5acb293e8da5` | PASS |

The fingerprint history artifact intentionally stores only:

- Path.
- Line count.
- File fingerprint.
- Pass / fail status.
- Error count.

It does not copy fixture text.

## 6. Reproduction Commands

Run from repository root.

### 6.1 Unit / Integration Tests

```bash
pytest tests/
```

Expected result:

```text
28 passed
```

### 6.2 Red-Team Drill Suite

```bash
bash tests/red-team-drills/run_all.sh
```

Expected result:

```text
All red-team drills completed
```

### 6.3 Recall Gate

```bash
python tests/red-team-drills/check_recall.py --min 0.92
```

Expected result:

```json
{
  "recall": 1.0,
  "effective_recall": 0.95,
  "detector_recall_estimate": 0.95,
  "false_positive_rate": 0.0,
  "min": 0.92,
  "passed": true,
  "failed_case_ids": [],
  "reasons": []
}
```

Note: `false_positive_rate` in `check_recall.py` reflects the positive corpus drill output. The negative corpus FP rate is measured separately below.

### 6.4 Fingerprint Gate

```bash
python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl --strict
```

Expected result:

```text
passed=true
synthetic_phi_corpus.jsonl lines=220
synthetic_phi_negative_corpus.jsonl lines=110
```

### 6.5 End-to-End SOP Dryrun

```bash
bash dryrun_e2e_v2.sh --ci
```

Expected result:

```text
Step 0-12 全部跑通
AUDIT_BUNDLE 已生成 + sha256 上链
```

### 6.6 Negative Corpus FP Scan

The current negative corpus scan is not yet baked into `run_all.sh`.

Reviewer can reproduce with:

```bash
python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('mcp/phi-detector').resolve()))
import server_v3
rows = [
    json.loads(line)
    for line in Path('tests/red-team-drills/fixtures/synthetic_phi_negative_corpus.jsonl')
    .read_text(encoding='utf-8')
    .splitlines()
    if line.strip()
]
fp = []
contract = []
for row in rows:
    response = server_v3.detect_v3(row['text'])
    spans = response.get('spans', []) if isinstance(response, dict) else []
    if spans:
        fp.append(row['id'])
    payload = json.dumps(response, ensure_ascii=False)
    for span in spans:
        start, end = span.get('start'), span.get('end')
        if 'text' in span or 'match' in span or 'matched_text' in span:
            contract.append(row['id'])
        if isinstance(start, int) and isinstance(end, int) and row['text'][start:end] in payload:
            contract.append(row['id'])
print({
    'negative_cases': len(rows),
    'false_positive_cases': len(fp),
    'false_positive_rate': round(len(fp) / len(rows), 4),
    'contract_violations': len(contract),
    'fp_case_ids': fp,
})
PY
```

Expected result:

```text
negative_cases=110
false_positive_cases=10
false_positive_rate=0.0909
contract_violations=0
```

The 10 FP cases are currently all in the build-artifact MRN-like category:

- `neg-build-artifact-mrn-like-001`
- `neg-build-artifact-mrn-like-002`
- `neg-build-artifact-mrn-like-003`
- `neg-build-artifact-mrn-like-004`
- `neg-build-artifact-mrn-like-005`
- `neg-build-artifact-mrn-like-006`
- `neg-build-artifact-mrn-like-007`
- `neg-build-artifact-mrn-like-008`
- `neg-build-artifact-mrn-like-009`
- `neg-build-artifact-mrn-like-010`

### 6.7 Latency Probe

Reviewer can reproduce with:

```bash
python - <<'PY'
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path('mcp/phi-detector').resolve()))
import server_v3
server_v3._RUNTIME = None
text = ('合成病历片段 ' * 70)[:1000]
server_v3.detect_v3(text)
durations = []
for _ in range(50):
    start = time.perf_counter()
    server_v3.detect_v3(text)
    durations.append((time.perf_counter() - start) * 1000)
durations.sort()
print(json.dumps({
    'samples': len(durations),
    'p50_ms': round(durations[len(durations)//2], 4),
    'p99_ms': round(durations[-1], 4),
    'threshold_ms': 100,
    'passed': durations[-1] < 100,
}, ensure_ascii=False))
PY
```

Observed result on 2026-05-21:

```json
{
  "samples": 50,
  "p50_ms": 0.4713,
  "p99_ms": 0.7586,
  "threshold_ms": 100,
  "passed": true
}
```

## 7. R1-R5 Self-Check

| Red line | Question | T1 answer | Evidence |
|---|---|---|---|
| R1 | Does T1 allow PHI to enter prompt raw? | No | Detector returns offsets, type, score, and `text_sha256`; no raw matched text in response envelope. |
| R2 | Does T1 bypass model allowlist routing? | No | T1 detector path is local / Presidio / regex; no LLM call added. |
| R3 | Does T1 weaken audit logging? | No | T1 does not change `mcp-audit-log`; dryrun audit bundle still passes. |
| R4 | Does T1 use compliant test data? | Yes | T1.7 fixtures are synthetic; T1.8 fingerprint checker strict mode passes. |
| R5 | Does T1 alter licensing? | No | No License file changes; Apache 2.0 / CC BY-SA 4.0 posture unchanged. |

## 8. Contract Checks

### 8.1 Raw Text Contract

The detector response envelope must not include raw matched text.

T1.5 tests assert that synthetic `CN_ID`, `CN_PHONE`, and `CN_MRN` values do not appear in serialized response payload.

T1.6 drill treats raw text in spans as a contract violation.

Final drill result:

```text
contract_violations=0
```

### 8.2 Synthetic Fixture Contract

Every fixture row must include:

- `id`
- `text`
- `expected`
- `source`
- `generator`

Every fixture row must set:

```json
{"source": "synthetic"}
```

T1.8 strict fingerprint check passes both T1.7 fixture files.

### 8.3 Recall Contract

The release threshold is:

```text
recall >= 0.92
```

Final T1 result:

```text
recall=1.0
effective_recall=0.95
```

### 8.4 FP Contract

The release threshold is:

```text
false_positive_rate <= 0.15
```

Final negative corpus result:

```text
false_positive_rate=0.0909
```

## 9. Residual Risks And Known Limitations

### 9.1 Regex-Only Fallback Does Not Detect Some Default Entities

When `zh_core_web_sm` is unavailable, the server enters regex-only fallback mode.

In this mode, the following forward-declared / default entities are skipped:

- `PERSON`
- `LOCATION`
- `ORGANIZATION`
- `CN_NAME`
- `BIOMETRIC_IDENTIFIER`
- `DEVICE_IDENTIFIER`
- `HEALTH_PLAN_BENEFICIARY_NUMBER`
- `MEDICAL_RECORD_NUMBER`
- `US_LICENSE_PLATE`

Operational impact:

- Current T1 acceptance does not depend on these entities.
- T2 can rely on the 10 implemented CN recognizers.
- T13 offline packaging should bundle `zh_core_web_sm` if richer NER is required.

### 9.2 CN_NAME Recognizer Is Still Forward-Declared

`fields.yml` declares `CN_NAME`, but T1.5 chose graceful skip rather than implementing the recognizer in the same PR.

Current status:

- `CN_NAME` is not implemented.
- Runtime skip is graceful.
- Tests assert graceful skip behavior.

Recommendation:

- Implement T1.5a as a follow-up leaf if T2 needs Chinese name detection.
- Keep T1.5a to two files: `mcp/phi-detector/recognizers/cn_name.py` and `tests/test_phi_detector_cn_name.py`.

### 9.3 spaCy Model Packaging Is Deferred

`zh_core_web_sm` is not installed automatically by current requirements.

Current behavior:

- Missing model produces warning.
- Server remains available.
- Regex-only mode detects the 10 implemented CN recognizers.

Recommendation:

- T13 offline packaging should bundle or document the spaCy model directory.
- Edge deployment should verify model availability before enabling name / organization / location workflows.

### 9.4 Forbidden Marker List Is Minimal By Default

T1.8 ships with default forbidden markers:

- `pacbio`
- `huangzeming`

These are sanitized placeholder markers.

Customer-specific markers are intentionally not committed.

Forks should inject extra markers through:

```bash
export MEDHARNESS_FORBIDDEN_MARKERS=cust1,cust2
```

or:

```bash
python tools/phi_fingerprint_check.py --forbidden-marker cust1,cust2 tests/red-team-drills/fixtures/*.jsonl
```

### 9.5 Negative FP Gate Is Not Yet Part Of `run_all.sh`

T1.7 measured the negative corpus FP rate manually.

Current state:

- Positive recall gate is automated in `run_all.sh`.
- Fingerprint gate is available as CLI.
- Negative FP scan is documented in this summary, but not yet wired into the red-team runner.

Recommendation:

- T8 CI cron or a future T1 hardening PR should promote negative FP scanning into a first-class gate.

### 9.6 MRN Recognizer Still Matches Build Artifact Shapes

The final negative corpus has 10 false positives, all in MRN-like build artifact cases.

Current result remains within threshold:

```text
10 / 110 = 0.0909 <= 0.15
```

Recommendation:

- If future T2/T8 workflows see noisy MRN matches in logs, add a post-processing demotion for artifact-like suffixes such as `.zip`, build cache paths, and CI filenames.

## 10. T1 -> T2 Handoff

T2 can rely on the following T1 outputs:

1. `server_v3.detect_v3(text)` returns a stable envelope with `spans` and `stats`.
2. Each span includes `start`, `end`, `entity_type`, `score`, and `text_sha256`.
3. The envelope does not include raw matched text.
4. The 10 implemented CN recognizers are registered through `load_cn_recognizers`.
5. `fields.yml` loads with 31 field definitions and strict schema validation.
6. Context post-processing deduplicates overlapping spans.
7. Placeholder suppression is applied in recognizers and post-processing.
8. CN bank values are Luhn / BIN guarded.
9. ICD and drug codes require clinical / medication context.
10. Recall drill output is machine-readable JSON.
11. `check_recall.py --min 0.92` enforces the release recall gate.
12. T1.7 positive and negative fixtures are available for regression tests.
13. `phi_fingerprint_check.py --strict` validates synthetic fixture compliance.
14. Red-team `run_all.sh` continues to pass.
15. Dryrun SOP still passes and produces audit bundle hash.

T2 should not assume:

1. `CN_NAME` is implemented.
2. spaCy Chinese model is installed.
3. Negative FP scan is wired into `run_all.sh`.
4. Real customer markers are present in the default forbidden marker list.
5. The detector can process real PHI in prompts without `phi-desensitize`.

## 11. Reviewer Checklist

Reviewer can independently verify T1 by running:

```bash
pytest tests/
bash tests/red-team-drills/run_all.sh
python tests/red-team-drills/check_recall.py --min 0.92
python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl --strict
bash dryrun_e2e_v2.sh --ci
```

Reviewer should inspect:

- `mcp/phi-detector/server_v3.py` response contract.
- `mcp/phi-detector/postprocess.py` span dedup and placeholder behavior.
- `tests/red-team-drills/drill_phi_recall.py` contract violation logic.
- `tools/phi_fingerprint_check.py` marker and fingerprint behavior.
- The two T1.7 fixture files for synthetic-only data posture.

Reviewer should confirm:

- No raw matched text is returned.
- No LLM calls were added in T1.
- No real PHI samples were introduced.
- No hook was disabled.
- No license file was changed.

## 12. Sign-Off

T1 phi-detector v3 production acceptance is met for v0.5.0 edge-tier work.

Sign-off block is recorded in `tasks.md`.

T1 is ready to hand off to T2 desensitization.
