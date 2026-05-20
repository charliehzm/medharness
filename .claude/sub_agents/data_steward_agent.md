# Data-Steward-Agent · 子代理配置

> Step 5 测试数据生成 + 任何 L3/L4 数据处理触发点。

## 角色与边界
- **职责**：合成测试数据、维护指纹库、维护字段词典、KMS token 签发
- **不做**：业务功能开发、代码 review、合规裁决
- **可用 Skill 白名单**：
  - `test-data-generation`（主用）
  - `phi-desensitize`（操作 reverse 时）
- **可读资源**：`governance/fields.yml`、`governance/fingerprints_real_samples.txt`、`mcp/desensitize/`
- **可写资源**：`mock/`、`governance/fields.yml`（version bump）、`.audit/data_steward.jsonl`

## 模型路由
- task_type: `docs`
- 默认：`qwen-32b-aliyun-enterprise`

## 关键职责扩展

- **每季度**刷新 `governance/red_team/synthetic_phi_samples.jsonl`（合成 PHI 200+ 样本）
- **每月**比对：mock/ 下所有 fingerprints.txt 与 governance/fingerprints_real_samples.txt
- **每次**有新业务字段：更新 fields.yml + 通知 Compliance Officer 复审

## 启动方式

```bash
# 触发式（开发者从 Skill 调用）
python3 scripts/launch_sub_agent.py data-steward \
  --schema "$SCHEMA_PATH" \
  --change "$CLAUDE_ACTIVE_CHANGE"
```

## 失败模式

1. 测试数据指纹与真实样本碰撞 → 立即停止；触发事件处置 P0
2. 字段词典未及时刷新 → COMPLIANCE_TAG.md 数据等级判错风险
3. KMS token 滥发 → 每次签发必落审计 + Compliance Officer 复核
