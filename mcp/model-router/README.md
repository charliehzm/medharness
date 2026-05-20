# mcp-model-router

> 按 MODEL_ALLOWLIST.json 路由 LLM 调用的核心闸门。

## 职责
- 输入：模型调用请求（task_type / change_id / payload / metadata）
- 路由：查 change 的 `MODEL_ALLOWLIST.json` → 找到合规模型 → 转发
- 拒绝：allowlist 不允许 / 模型部署位置不符 → 直接拒绝（不告诉调用方它本来想调谁，避免泄露策略）

## 设计要点
1. **强一致性**：allowlist 由 `compliance-precheck` Skill 注入，运行时不可热改
2. **task_type 路由**：coder / reviewer / architect / docs / compliance 五类，各自独立 allowlist
3. **PHI 二次校验**：转发前再过一遍 phi-detector；命中 → 拒绝（任何 PHI 即使在 allowlist 模型也不应裸入）
4. **审计强制**：每次路由决策落 `routing_log.jsonl`（含决策、原因、命中规则）
5. **fail-closed**：allowlist 缺失 / KMS 不可达 / phi-detector 不可达 → 一律拒绝

## 接口

### `route`
```jsonc
// request
{
  "task_type": "coder | reviewer | architect | docs | compliance",
  "change_id": "...",
  "prompt": "...",
  "options": {
    "tier_override_allowed": false,
    "trace_id": "..."
  }
}

// response (allow)
{
  "decision": "allow",
  "model_id": "qwen-32b-private",
  "deployment": "private_cloud",
  "endpoint": "https://internal.qwen/v1/chat",
  "routing_log_id": "..."
}

// response (deny)
{
  "decision": "deny",
  "reason": "phi_in_prompt | model_not_in_allowlist | allowlist_missing | tier_mismatch",
  "routing_log_id": "..."
}
```

### `health`
返回 server 状态、当前活跃 change 数、phi-detector / KMS 可达性。

## 决策算法（伪代码）
```
def route(req):
    if change_id missing or allowlist missing:
        return deny("allowlist_missing")
    if not allowlist_active(change_id):
        return deny("allowlist_expired")
    phi = phi_detector.detect(req.prompt)
    if phi.blocking_recommendation:
        return deny("phi_in_prompt")
    candidates = allowlist[req.task_type]
    if not candidates:
        return deny("no_candidate_for_task_type")
    chosen = pick_by_policy(candidates)  # 健康度/成本/亲和度
    log_routing(req, chosen, phi)
    return allow(chosen)
```

## 部署
- M2：单实例，配置文件方式注入 endpoint 列表
- M3+：HA + 多区域

## 待开发清单（M2）
- [ ] 实现 route / inject_allowlist / health
- [ ] 集成 phi-detector
- [ ] 路由日志 schema 与 AUDIT_BUNDLE.models.routing_log.jsonl 对齐
- [ ] 失败演练：phi-detector 挂掉时 deny 100%
- [ ] 性能：P99 ≤ 30ms（不含转发到模型）

## 自审清单
- [ ] 任何 deny 响应都给 reason，但不暴露 allowlist 内容
- [ ] inject_allowlist 调用必须带 Compliance Officer 签发的 token
- [ ] M1 占位用环境变量传 token；M2 起强制 mTLS + 双因子
