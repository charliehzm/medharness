# mcp-desensitize

> 脱敏 + 反向映射表管理的 MCP server。`phi-desensitize` Skill 的执行后端。

## 职责
- 输入：含 PHI/PII 的文本或结构化载荷 + 数据等级
- 输出：脱敏后载荷 + 加密反向映射表的 id（不返回明文映射）
- 反向：受控环境下用 map_id + KMS 凭据反查

## 设计要点
1. **占位符稳定性**：同会话内同源值 → 同占位符（保留关系），跨会话/跨 change 不保留（避免可链接）
2. **类型保留**：placeholder 形如 `{{PT_A1}}`、`{{ID_B7}}`、`{{DR_C2}}`，下游模型能推断类型
3. **日期保留间隔**：日期不用纯占位，用 per-patient 随机 offset 保留时间序列
4. **fail-closed**：任何脱敏内部错误 → 拒绝返回明文，调用方收到 error

## 接口

### `desensitize`
```jsonc
// request
{
  "payload": "string or json",
  "tier": "L3 | L4",
  "change_id": "...",
  "preserve_intervals_for": ["date_of_admission", "date_of_discharge"]   // optional
}

// response
{
  "desensitized": "...",
  "map_id": "uuid",
  "map_ref": "kms://path/to/encrypted/map",
  "residual_risk": [
    {"reason": "free-text low-confidence hit", "span": [...]}
  ]
}
```

### `reverse`
```jsonc
// request
{
  "desensitized": "...",
  "map_id": "uuid",
  "kms_token": "..."     // 单次令牌，受控环境签发
}

// response
{
  "original": "..."
}
```

需通过 Compliance Officer 签发的 KMS token 才能调用 reverse。reverse 调用全部落审计。

### `health`
返回 server 状态、KMS 连通性、rules+classifier 版本。

## 部署
- M2：单实例，与 phi-detector 同主机
- M3+：内网 K8s + KMS 集成

## 待开发清单（M2）
- [ ] 实现 desensitize（依赖 phi-detector 命中清单）
- [ ] 实现 KMS 集成（AES-256-GCM 加密 map）
- [ ] 实现 reverse（带 token 校验）
- [ ] CLI 形态供 CI 与 phi-desensitize Skill 调用
- [ ] 红队测试：反演率 < 0.1%

## 自审清单
- [ ] map_id 与 change_id 强绑定，跨 change 不可复用
- [ ] reverse 调用 100% 走审计，5xx 也要记录
- [ ] map 文件生命周期与 change AUDIT_BUNDLE 一致（6 年）
