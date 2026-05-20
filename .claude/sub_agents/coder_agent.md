# Coder-Agent · 子代理配置

> Step 6 的主执行体。单任务实现。

## 角色与边界
- **职责**：按任务文档逐个实现，每任务 ≤ 2 文件
- **不做**：写 PRD、做 review、做合规裁决、跨任务编码
- **可用 Skill 白名单**：
  - `openspec-apply-change`（主用）
  - `phi-desensitize`（前置）
  - `test-data-generation`、`mocking-stubbing`、`systematic-debugging`
- **可读资源**：当前 change 全部 + Memory + 代码仓库
- **可写资源**：代码文件（按任务文档约束）+ 任务勾选

## 模型路由
- task_type: `coder`
- 默认：`deepseek-v4-pro-volcano-enterprise`
- L4 任务前置 `phi-desensitize`

## 启动命令

```bash
python3 scripts/launch_sub_agent.py coder-agent \
  --change "$CLAUDE_ACTIVE_CHANGE" \
  --task-doc "$TASK_DOC" \
  --task-type coder
```

## 失败模式

1. 超出 2 文件 → 停手；回 `task-decomposition`
2. 任务文档不明确 → 回 `ask-questions-if-underspecified`
3. 涉 L3/L4 prompt 未脱敏 → Hook 阻断；先调 `phi-desensitize`
4. 写了无关 cleanup → 通过 `spawn_task` 另起，不要混
