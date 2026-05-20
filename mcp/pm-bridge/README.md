# mcp-pm-bridge

> 与 PM 工具（Jira / 飞书 / 钉钉 / Notion）对接的 MCP server（M5 上线）。

## 职责
- 双向同步：PRD / change / 任务状态 ↔ PM 工具
- PRD 撰写后自动建 Jira ticket / 飞书任务
- AUDIT_BUNDLE 归档后回写"已交付"状态
- 合规事件升级 → 自动建工单到 Compliance Officer

## 接口

### `sync_change`
```jsonc
{"change_id": "...", "direction": "to_pm | from_pm"}
// → {"updated": {...}}
```

### `create_compliance_ticket`
```jsonc
{"severity": "P0|P1|P2", "summary": "...", "evidence": "audit_log://..."}
// → {"ticket_id": "..."}
```

### `notify`
```jsonc
{"channel": "feishu | dingtalk", "audience": "tech-committee | compliance-committee | skill-owners",
 "subject": "...", "body": "...", "evidence": "..."}
```

## M5 上线最小实现
- 后端：Jira / 飞书 / 钉钉 SDK（按公司实际工具）
- 单向 first（to_pm），双向 next
- 所有 sync 落 mcp-audit-log

## 待开发清单
- [ ] 工具 SDK 适配
- [ ] 单向 sync
- [ ] 通知模板（含合规事件 P0 模板）
- [ ] 双向 sync + 冲突解决

## 自审清单
- [ ] 任何 sync 必经数据分级检查（L3/L4 字段不可同步到外部 PM 工具）
- [ ] 合规事件通知不走公网（钉钉 / 飞书企业内 IM）
