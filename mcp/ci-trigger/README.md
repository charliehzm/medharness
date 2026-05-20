# mcp-ci-trigger

> Stage feature flag + CI 流水线触发 MCP（M4 上线）。

## 职责
- 调度 stage flag（`stage3_orchestrator_minimal_execution` 类）
- 触发 CI 流水线（`scripts/verify_stage_fixtures.py`、`scripts/ci_check_generated_diff.py`）
- 灰度发布：`dev → staging → canary → full`
- 回滚 hook：失败时自动关 flag

## 接口

### `set_flag`
```jsonc
// request
{"flag": "stage3_orchestrator_minimal_execution", "env": "canary", "value": true,
 "change_id": "...", "actor": "..."}
// response
{"prev_value": false, "new_value": true, "audit_id": "..."}
```

### `trigger_pipeline`
```jsonc
{"pipeline": "verify_stage_fixtures | ci_check_generated_diff | full_release",
 "args": {"change_id": "...", "stage": 3},
 "actor": "..."}
// → {"run_id": "...", "status_url": "..."}
```

### `rollback_stage`
```jsonc
{"change_id": "...", "stage": 3, "reason": "..."}
// → {"rolled_back_from": "canary", "to": "staging", "audit_id": "..."}
```

## M4 上线最小实现
- 后端：GitHub Actions / Jenkins API（按团队选型）
- Flag 后端：环境变量 / Consul / 数据库
- 审计：每次调用落 mcp-audit-log

## 待开发清单
- [ ] flag 后端 + API 适配
- [ ] CI 触发集成
- [ ] 灰度顺序与回滚自动化
- [ ] 与 Stage 3 evidence 集成
