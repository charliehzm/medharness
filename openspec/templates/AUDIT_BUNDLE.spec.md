# AUDIT_BUNDLE · Schema

> Step 12 审计冻结产物的标准 schema。
> `audit-snapshot` Skill 按此 schema 打包。

---

## tar.gz 内目录

```
AUDIT_BUNDLE_<change-name>_<utc-iso8601>.tar.gz
├── manifest.json
├── COMPLIANCE_TAG.md
├── COMPLIANCE_REPORT.md
├── proposal.md
├── tasks.md
├── specs/                       # 全部 spec.md
├── diff.patch                   # 完整代码 diff
├── test_results.json            # 测试通过状况
├── prompts/                     # 所有 LLM 调用记录（gzip 压缩）
│   ├── <timestamp>_<skill>.jsonl.gz
│   └── ...
├── routing_decisions.jsonl      # model-router 决策日志
├── hook_invocations.jsonl       # 9 Hook 触发记录
├── lineage_graph.json           # PRD→Spec→Task→Code→Test→Deploy 血缘
└── hashchain.txt                # 链式哈希（每步 sha256）
```

## manifest.json schema

```json
{
  "version": "1.0",
  "change_name": "string",
  "change_id": "uuid",
  "timestamp": "iso8601",
  "compliance": {
    "data_levels": ["L1", "L2", "L3", "L4"],
    "model_allowlist": ["model_id_1", "model_id_2"],
    "phi_redactions": 42,
    "high_risk_findings": 0,
    "medium_risk_findings": 1
  },
  "models_used": [
    {
      "model_id": "qwen-32b-v2.5-instruct",
      "vendor_family": "alibaba",
      "purpose": "matcher",
      "calls": 127
    }
  ],
  "lineage": {
    "prd": "sha256:...",
    "specs": ["sha256:..."],
    "tasks": ["sha256:..."],
    "code_diff": "sha256:...",
    "tests": "sha256:..."
  },
  "hashchain": {
    "head": "sha256:...",
    "length": 12
  },
  "signers": [
    {"role": "proposer", "name": "...", "date": "..."},
    {"role": "compliance", "name": "...", "date": "..."},
    {"role": "tech_lead", "name": "...", "date": "..."}
  ]
}
```

## hashchain.txt 格式

```
step_0_compliance_precheck   sha256:<hash>
step_1_prd                   sha256:<hash>
step_2_tdd                   sha256:<hash>
...
step_12_archive              sha256:<hash_head>
```

每行 = 该 Step 产物的 sha256；上一行的 hash 拼到下一行哈希源头，构成链。
任一环节被篡改 → 链断 → 不可重放。

## 大小目标

- 压缩前：< 200MB
- 压缩后（gzip）：< 20MB
- prompts/ 占 60-70%（已 gzip）

如超 20MB → 触发 `audit-snapshot` 的 prompt 抽样模式（保留首/末 + 关键决策点）。

## 可重放

任何 AUDIT_BUNDLE 必须满足：
- 用 manifest 中相同模型 + 相同 prompts 调用 LLM
- 得到与 routing_decisions 相同结果（± temperature 容差）
- 哈希链完整
- 100% 重放成功率（M6 + KPI）
