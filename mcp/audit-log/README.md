# mcp-audit-log

> Append-only · WORM · 哈希链 · HIPAA/PIPL 6 年保留

## 职责
- 接收 audit 事件（来自 hooks / skills / mcp-servers）
- 写入 append-only 存储；幂等 id 检测
- 维护哈希链：每条新事件包含上一条事件的 hash
- 提供 query 接口（按 change_id / time / event_type）
- 提供 verify 接口（重算哈希链验证完整性）

## 存储后端选择（M3 决策）
- **本地 M2 占位**：append-only JSONL，文件不可修改（chattr +a）
- **M3 生产**：ClickHouse + 对象存储 WORM（阿里云 OSS 不可变 / S3 Object Lock）
- **M4+**：上链（可选）—— 区块链锚定 ROOT_SHA256，最强不可篡改

## 事件 schema

```jsonc
{
  "id": "uuid",                           // 服务器分配
  "ts": "2026-05-16T09:00:00Z",
  "session_id": "...",
  "change_id": "...",
  "event_type": "tool_call | model_call | skill_call | phi_block | routing_decision | bundle_seal | reverse_invocation | compliance_finding",
  "actor": "claude-code | mcp-* | human-<id>",
  "payload": { /* 事件特定字段 */ },
  "prev_hash": "sha256:...",              // 哈希链
  "self_hash": "sha256:..."               // sha256(canonical_json(self_without_self_hash))
}
```

## 接口

### `append`
- 输入：事件（无 id / prev_hash / self_hash）
- 输出：含完整哈希链字段的事件
- 失败：返回 error；调用方必须重试（fail-loud）

### `query`
- 输入：change_id / time_range / event_type
- 输出：事件流 + chain root hash

### `verify`
- 输入：change_id 或 time_range
- 输出：完整性结论 + 失配 id 列表

### `seal_bundle`
- 输入：bundle ROOT_SHA256 + manifest hash
- 输出：WORM receipt（含 storage URI + receipt hash）
- 由 `audit-snapshot` Skill 在 Step 12 调用

## 待开发清单（M3）
- [ ] WORM 后端（先 chattr +a，后切 ClickHouse + OSS）
- [ ] 哈希链算法实现
- [ ] query/verify/seal_bundle 三端点
- [ ] 6 年保留策略 + 自动归档冷存储
- [ ] 演练：模拟篡改 → verify 必须失败

## 自审清单
- [ ] 任何 write 失败必须返回 error；不允许"静默存到内存"
- [ ] seal_bundle 必须返回可独立验证的 receipt
- [ ] query 必须脱敏敏感字段（payload 内容不返回 PHI）
