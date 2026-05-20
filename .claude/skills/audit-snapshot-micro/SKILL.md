---
name: audit-snapshot-micro
description: >
  Use this skill at Step μ5 of the 5-step micro SOP to produce a lightweight
  MICRO_AUDIT.json (vs the full AUDIT_BUNDLE.tar.gz). Records diff hash, test
  result, MICRO_TAG, and writes to mcp-audit-log under event_type
  `micro_change_seal`. Chinese trigger examples: "micro 归档", "Step μ5",
  "轻量审计冻结". Do NOT use for full changes (12-step SOP uses audit-snapshot).
  Success = MICRO_AUDIT.json written + mcp-audit-log receipt.
compatibility: Requires git diff + mcp-audit-log.
metadata:
  version: "1.0"
  owner: "harness-engineer"
  category: "compliance-gate-micro"
  maturity: "production"
  sop_step: "μ5"
  hard_gate: true
  outputs: "MICRO_AUDIT.json + mcp-audit-log entry"
---

# Audit Snapshot · Micro 版

## 输出

`MICRO_AUDIT.json`（路径：紧靠 micro-change 的相关 PR 或 micro 目录）：

```json
{
  "schema_version": "1.0",
  "type": "micro_change",
  "change_name": "...",
  "files_changed": ["..."],
  "diff_sha256": "sha256:...",
  "test_result": "PASS|FAIL",
  "test_summary": {"unit": N, "passed": N},
  "developer": "...",
  "parent_change": "openspec/changes/<...>",  // optional
  "archived_at": "ISO-8601",
  "mcp_audit_log_receipt": {
    "row_id": "...",
    "self_hash": "sha256:..."
  }
}
```

## 流程

1. 计算 diff 的 sha256（`git diff --no-color`)
2. 收集 test 输出（pytest / npm test 简化输出）
3. 调 `mcp-audit-log append` （event_type: `micro_change_seal`）
4. 写 MICRO_AUDIT.json 到 PR 关联位置

## 与完整版的差别

| 项 | audit-snapshot (12 步) | audit-snapshot-micro |
|---|---|---|
| Bundle | tar.gz（含 prompts/changes/lineage/...） | 单 JSON |
| 大小 | 平均 87MB | < 5KB |
| Hash 链 | 内部哈希链 + ROOT_SHA256 | 单 diff_sha256 |
| WORM | seal_bundle 端点 | append 普通 event |
| 重放 | 4 小时可重放 | 不要求完整重放 |
| 保留 | 6 年 | 6 年（同） |

## 不允许

- 用 micro 包装大型变更（先 sop_router 校验）
- 跳过 mcp-audit-log
- 自定义 schema 字段（必须按上表）

## 抽查

Compliance Officer 月度抽 10%：
- diff_sha256 与 git 实际 diff 比对
- test_result 与 CI 历史核对
- 发现伪声明 → 涉事开发者培训 + 通道使用资格暂停 1 月
