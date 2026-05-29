# Spec · A0 · 只读聚合 API 契约（前后端的缝）🔒

> 单 owner（charliehzm / 我）。BE 照此实现端点，FE 照此 mock。**契约变更走单 owner + 版本 bump**，Codex 不得自行改。
> 这是 Console 第一次把闸门内部数据呈现给人 → **新的 PHI 出仓边界**，schema 白名单强制。

---

## Purpose

定义 Console 调用的全部**只读** HTTP 端点的 request / response schema。所有返回体经显式字段白名单序列化，**永不含原始 PHI / 安全事件 payload 原文 / 反向映射表**。

## 通用约定

- Base path：`/api/v1`，全部 `GET`（只读；唯一例外见 §导出）
- 鉴权：内网部署，沿用 edge tier 的反代鉴权；契约层不定义账号体系
- 时间：ISO 8601 UTC
- 返回体只允许三类内容：**占位符**（`__NAME_a1__`）/ **哈希引用**（`routing#a1b2`）/ **聚合数与分类标签**
- 错误体：`{"error": {"code": str, "msg": str}}`，**msg 不得含系统版本 / 栈 / 内部路径**（ADR-17）

## 端点组

### 1. 态势 `GET /posture`
```json
{
  "composite": 92,
  "compliance_score": 96,
  "security_score": 89,
  "gates": [
    {"id":"phi-inbound","group":"compliance","status":"green","metric":"100%","desc":"泄漏拦截率·220 样本"},
    {"id":"desensitize","group":"compliance","status":"green","metric":"0.02ms"},
    {"id":"model-router","group":"compliance","status":"green","metric":"11/11"},
    {"id":"injection","group":"security","status":"green","metric":"100%"},
    {"id":"outbound-safety","group":"security","status":"planned","metric":"🚧 v0.6","built":false},
    {"id":"rate-limit","group":"security","status":"planned","metric":"🚧 v0.6","built":false}
  ],
  "alerts": [
    {"cat":"security","type":"注入","level":"warn","summary":"prod-dify 今日拦截 3 次注入尝试","payload":null}
  ]
}
```
> `built:false` 的闸门前端必须渲染 🚧；`alerts[].payload` **永远 null**（安全事件不回显）。

### 2. 流量聚合 `GET /traffic?window=1h&ctx=all|dev|prod`
```json
{
  "inbound": {"upstreams":[{"name":"Dify RAG","ctx":"prod","rate":1200}],
              "gate":{"hit":47,"blocked":3,"passed":1627},
              "downstream":[{"name":"私有 Qwen","note":"脱敏后"}]},
  "outbound": {"built":false, "note":"🚧 v0.6 规划", "gate":{"phi_reflow":0,"harmful":0,"hallucination":0}}
}
```

### 3. 事件流 `GET /events?cat=all|comp|sec&ctx=...&limit=50`
```json
{"events":[
  {"ts":"...","cat":"comp","status":"green","upstream":"dify-rag","ctx":"prod","level":"L3","action":"脱敏后路由 qwen-max","ref":"routing#a1b2"},
  {"ts":"...","cat":"sec","status":"red","upstream":"dify-rag","ctx":"prod","sec_type":"注入","action":"检索内容含可疑指令→隔离","ref":"inj#c3d4","payload":null}
]}
```
> `level` 仅合规事件有；`sec_type` ∈ {注入,滥用,输出}；`payload` 对安全事件**永远 null**。

### 4. 审计血缘 `GET /audit/{ref}` （ref 如 routing#a1b2 / 阻断#c3d4 / desens#e5f6）
```json
{"ref":"routing#a1b2","title":"脱敏后路由（prod-dify-rag）",
 "nodes":[{"ico":"📥","t":"入站请求","s":"prod-dify-rag"}, {"ico":"🔐","t":"脱敏","s":"AES-256-GCM"}],
 "hash":"哈希链完整·block #18,420·daily verify 通过",
 "details":[{"k":"数据分级","v":"L3"},{"k":"占位符样例","v":"__NAME_a1__ __MRN_b2__"}]}
```
> `details[].v` 只允许占位符 / 哈希 / 聚合；**反向映射表与原始 PHI 不出现**。未命中 → 404 `{"error":{"code":"not_found"}}`。

### 5. 上游状态 `GET /upstreams`
```json
{"upstreams":[{"name":"prod-dify-rag","ctx":"prod","protocol":"openai","status":"green","traffic_today":8247,"phi":"命中 312 / 拦 5"}]}
```

### 6. 配置（只读快照）`GET /config/{section}`
section ∈ {scene,models,fields,thresholds,retention,injection,output,quota,upstream,approval}
> 返回当前策略快照供 Console 展示与 diff 预览。**Console 不经此改配置**——写操作只产生「提交审批」动作（见下），实际变更仍走 PR + 审批流 + Hook，不旁路。

### 导出（唯一非 GET）`POST /audit/export`
- 触发 AUDIT_BUNDLE 打包（脱敏 prompt history / model versions / routing decisions / 哈希链）
- **此动作必须落 mcp-audit-log**（谁/何时导出）
- 返回 `{"bundle_id":str,"status":"packing|ready","sha256":str}`；产物本身 0 PHI（已脱敏）

### 提交审批（配置变更的唯一写口）`POST /config/{section}/propose`
- body = diff（变更前后）
- 返回 `{"approval_id":str,"level":"单签|会签|三签","status":"queued"}`
- **不直接改内核配置**；落审计；审批前不生效、可回滚

---

## Constraints

- C1 · 任何端点返回体经**显式字段白名单**序列化；未在白名单字段不得出现（ADR-15）
- C2 · 安全事件 `payload` 字段**恒为 null**（防二次传播）
- C3 · 无端点返回原始 PHI / 反向映射表；只占位符 + 哈希 + 聚合
- C4 · 错误体 msg 不泄露系统 / 版本 / 栈 / 路径
- C5 · 未建能力（outbound / quota）以 `built:false` + `status:"planned"` 标注，由前端渲染 🚧
- C6 · 新增 red-team drill `api-phi-exfil`：遍历所有端点返回体做 PHI 扫描，期望 0 命中

## DoD

契约打 version tag · mock server 可起 · `api-phi-exfil` drill 通过（0 PHI）· FE 能照 mock 渲染全部 7 视图
