---
name: test-data-generation
description: >
  Use this skill at Step 5 of the v2 SOP to generate stage-isolated synthetic
  test fixtures (mock data) for an OpenSpec change. Outputs fixtures into
  mock/阶段N-<名称>/, computes fingerprints, declares synthetic-only source,
  and runs the fingerprint match against the real-sample fingerprint library.
  Chinese trigger examples: "生成测试数据", "Mock 数据生成", "Step 5",
  "合成 fixture", "生成 mock", "测试数据 generation". Do NOT use to sample
  from production, do NOT use real PHI as seed even after redaction.
  Success = fixtures generated, fingerprints computed, fingerprint match
  against real-sample library returns zero collisions, source declaration
  marked synthetic-only.
compatibility: Requires file write under mock/. Optional: hash-compare tool for fingerprint check.
metadata:
  version: "1.0"
  owner: "data-steward"
  category: "spec-helper"
  maturity: "production"
  sop_step: 5
  hard_gate: true
  outputs: "mock/阶段N-<名称>/{*.jsonl,*.csv,fingerprints.txt,source_declaration.md}"
---

# Test Data Generation

Generates fixtures the change can be tested against, with the strong invariant: **never reversible to real patients**.

## Generation modes (pick one)

| Mode | When | Risk |
|---|---|---|
| Pure synthetic (faker-style) | Default | Low |
| Schema-driven random | When distribution matters less than shape | Low |
| Distribution-matched synthetic (DP) | When ML features depend on realistic distributions | Medium — guard against re-identification |
| Real → fully-decoupled (rare) | Only with Data Steward signoff + 18-id strip + outlier removal + k-anonymity ≥ 5 | High — extra audit |

**Forbidden mode**: "sample from production then mask names". Cannot prevent re-identification. Refuse.

## Workflow

1. Read schema from change specs (data model section in design.md).
2. Choose generation mode; document choice in `source_declaration.md`.
3. Generate per-stage directory: `mock/阶段N-<名称>/`.
4. For each output file, compute fingerprints (sha256 of canonical-sorted rows).
5. Compare fingerprints against the real-sample fingerprint library (held by Data Steward).
6. **If any collision/near-match**: stop, escalate, do not write fixtures.
7. Else: write fixtures + fingerprints.txt + source_declaration.md.

## Source declaration template

```markdown
# Source Declaration · 阶段N-<名称>

- 生成模式: <pure-synthetic / schema-driven / distribution-matched / real-decoupled>
- 生成时间: <ts>
- 生成器: <tool + version>
- 真实样本接触: 否（默认）/ 是（需 Data Steward 签字）
- 指纹核验: <PASS / FAIL>，对比库版本 <x.y>
- 合规等级承诺: 本数据集等同 L1，可在所有 allowlist 模型上使用
```

## Common failure modes

1. **"Looks real" generators** — Faker with locale 'zh_CN' produces plausible Chinese names but no link to real patients; this is fine. The trap is when devs *seed* with real values.
2. **Distribution-matched without DP** — releasing means/variances can leak. Mitigation: differential privacy budget recorded in source declaration.
3. **Forgetting fingerprint match** — fixtures written but never checked. Mitigation: this skill MUST run fingerprint compare before write.
4. **Cross-stage mixing** — same fixture used across stages. Mitigation: per-stage directory; do not symlink.
