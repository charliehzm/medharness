# Spec · patient-match

## Purpose
将含 PHI 字段的患者记录归并到统一 `match_id`，全程不裸露 PHI。

## Inputs
- `patient_record`: dict
  - 必填：`patient_name` `cn_id` `cn_phone`
  - 选填：`cn_mrn`

## Outputs
- `match_id`: str（脱敏后的统一 ID）
- `confidence`: float ∈ [0, 1]
- `audit_handle`: str（审计句柄，事后可重放）

## Constraints
- C1 · 任何字段必须先经 `mcp-desensitize` 才能进入 LLM prompt
- C2 · 单条请求 < 200ms（P99 < 500ms）
- C3 · 错配率（合成验证集 5k 条）< 0.5%
- C4 · 模型仅在 allowlist 内（Qwen 32B 本地 / 私有 DeepSeek）

## Acceptance criteria
- AC1 · Verify 一次过 ≥ 75%
- AC2 · 5000 条合成数据集错配 < 25 条
- AC3 · 100% 请求落 audit-log
- AC4 · red-team 演练（10 条带 PHI 注入）→ 全部阻断 + 告警

## Non-goals
- 跨医院数据交换
- 模糊语义匹配（如"张三/張三"繁简体；本期仅同体内容）
