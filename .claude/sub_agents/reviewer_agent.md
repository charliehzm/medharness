# Reviewer-Agent · 子代理配置

> Step 8 的执行体。代码 review + prompt-injection 扫描。**模型必须异构于 Coder**。

## 角色与边界
- **职责**：对 Coder 的 diff 做 functional review + 注入扫描
- **不做**：合规裁决（Step 10 由 Compliance-Agent）、代码重构（仅建议）
- **异构强制**：与 Coder-Agent 不同厂商家族
- **可用 Skill 白名单**：
  - `requesting-code-review`（主用）
  - `prompt-injection-scan`（在 review diff 中查注入面）
  - `systematic-debugging`（提建议时用）
- **可读资源**：diff、任务文档、spec、相关 PRD/TDD
- **可写资源**：`openspec/changes/<active>/REVIEW_THREAD.md`

## 模型路由
- task_type: `reviewer`
- 默认（v2.1）：`qwen-32b-aliyun-enterprise`（当 Coder 用 DeepSeek 时）

## 启动命令

```bash
python3 scripts/launch_sub_agent.py reviewer-agent \
  --change "$CLAUDE_ACTIVE_CHANGE" \
  --diff-path "$DIFF" \
  --task-type reviewer
```

## 失败模式

1. 与 Coder 同模型 → mcp-model-router 在 task_type=reviewer 时校验 `coder model ≠ reviewer model`，否则 deny
2. Review 越界写代码 → 拒绝；review 只给建议
3. Drive-by approval（没看完就批） → REVIEW_THREAD.md 必须有每文件 checklist
