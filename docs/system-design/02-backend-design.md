# MedHarness 后端设计

> **状态**：DRAFT · 与代码现状对齐。**已建** = mcp/ 6 服务 + 契约；**待建** = 网关焊接(C1/C2) + A0 后端(C9) + ClickHouse/Redis/KMS。
> **锚点**：[01-architecture.md](01-architecture.md) §4 Hook 顺序契约（脊柱）· A0 契约 [web/src/api/contract/](../../web/src/api/contract/)。

---

## 1. 后端分层

```
nginx DMZ (TLS·allowlist)
   ├─ /v1/*            → new-api fork (C1·Go 网关底座)
   │                       └ relay 内置 Go 合规中间件 (C2·进程内) 强制 §D.1
   │                            pre:  phi-detector→desensitize→model-router→injection
   │                            post: outbound-safety
   │                            每步 → audit-log
   └─ /api/v1/*        → A0 聚合 API 服务 (C9·Python/FastAPI)
                            └ 只读聚合 ClickHouse/router/audit → 0-PHI 出参
控制面（medharness_internal·不直连上游）：
   phi-detector · desensitize · model-router · audit-log · injection-scan · outbound-safety
存储：ClickHouse(_audit_log/_phi_lookup) · Redis(脱敏体缓存) · KMS/FileKeyProvider(密钥)
```

---

## 2. 网关焊接（C1 new-api fork + C2 gate-orchestrator）— Phase A 核心

### 2.1 焊入点
new-api 的 relay 处理链（`relay/` 控制器）在「收到请求 → 选渠道 → 外呼 provider → 返回」之间。我们**在最前插 pre-call、最后插 post-call**：

```go
// new-api fork · relay middleware（伪码）
func ComplianceRelay(c *gin.Context) {
    body := readBody(c)
    decision := gate.PreCall(body)          // ① HTTP→C2，阻塞
    if decision.Action == "deny" {          // 不变量①：deny 即静默
        audit.Log("deny", decision);  c.JSON(deny);  return   // 不外呼/不写cache/不落上游日志
    }
    c.Set("route_decision", decision)        // 不变量②：底座只执行
    resp := relayWithDecision(c, decision)   // ②cache ③retry(限set) ④dispatch ⑤log，全在 allowed_model_set 内
    safe := gate.PostCall(resp, decision)    // ⑥ HTTP→C2
    audit.Log("complete", safe.AuditLabels)
    c.JSON(safe.Body)
}
```

### 2.2 合规中间件（C2 · new-api 内置 Go · 已决）
**裁定**：gate 编排做成 **new-api relay 链内的 Go 中间件**（进程内），**不**做独立服务——enforcement 在网关内不可绕过、少一跳省延迟预算（§G.2）。中间件按 §D.1 直接调控制面 Python 服务（localhost）：

```
pre-call（阻塞·rule-first）:
  phi-detector.detect → desensitize.encrypt(若命中) → model-router.evaluate → injection.detect
    → RouteDecision | {action:"deny", reason_code}   （任一失败/超时 → fail-closed deny 或落敏感通道）
post-call:
  outbound-safety.classify → {action:pass|block|warn, body}
全程 → audit-log.log_event（外呼前后双写）
```

**RouteDecision（结构化·底座不可覆写）**：
```jsonc
{ "decision_id": "uuid", "lane": "normal|sensitive", "data_level": "L1..L4",
  "allowed_model_set": ["qwen-max-2026", "deepseek-v4-pro"],   // 底座成本排序仅限此集合
  "provider_policy": { "region": "境内", "no_retention": true, "no_training": true },
  "desensitized": true, "map_id": "envelope-id-or-null",
  "audit_labels": { "input_hash": "...", "lane": "...", "model_class": "..." } }
```

> **inline 仅 rule-first**：重 NLP（phi 深检 / 注入 LLM 分类 / B1）异步或抽样，不进首字节阻塞路径（守 §G.2 预算）。**开放项 ②**：C3–C8 需对 Go 中间件暴露稳定 HTTP/JSON（或 gRPC）+ 超时/重试/熔断契约——落 **ADR-18**。

---

## 3. 控制面服务（已建·mcp/）

| 服务 | 入口 | 核心接口 | 关键内部 |
|---|---|---|---|
| **phi-detector** | [mcp/phi-detector/server_v3.py](../../mcp/phi-detector/) | `detect_phi_v3(text) → {entities:[{type,start,end,score,hash}], 0 原文}` | Presidio + `recognizers/cn_*.py`（jieba 医疗上下文）+ `fields.yml`（28 实体 + 上下文加权）+ `postprocess.py` |
| **desensitize** | [mcp/desensitize/server_v2.py](../../mcp/desensitize/) | `encrypt_mapping(spans) → {placeholders, map_id}`；`decrypt_mapping(map_id)`（受控授权） | `crypto_envelope.py`（AES-256-GCM + 规范 AAD: Algorithm/ChangeId/KeyId/MapId/schema_version）+ `key_provider/file_provider.py`（多代轮换）+ `sql/phi_lookup.sql` |
| **model-router** | [mcp/model-router/server_v2.py](../../mcp/model-router/) | `evaluate_route(RouteRequest) → RouteDecision` | `policy.py`（PolicyCore 5 层·见 §4）+ `allowlist.py`（HotAllowlist 热加载）+ `heterogeneity.py` + `limits.py`（RateLimiter+CircuitBreaker）+ `vendor_families.yml` |
| **audit-log** | [mcp/audit-log/server_v2.py](../../mcp/audit-log/) | `log_event(EventLog) → row_id` | 三态机 NORMAL→FALLBACK→BACKFILL + `hashchain.py`（SHA-256·GENESIS_PREV_HASH）+ `clickhouse_writer.py` + `fallback_writer.py`（PID lock）+ `event_types.yml` |
| **prompt-injection-scan** | [mcp/prompt-injection-scan/detector.py](../../mcp/prompt-injection-scan/) | `detect_injection(text) → {blocked, category}` | 5 类（indirect_injection/tool_abuse/role_escalation/jailbreak/encoding_obfuscation）+ 混淆字符归一·不回显 payload |
| **outbound-safety** | [mcp/outbound-safety/classifier.py](../../mcp/outbound-safety/) | `classify(response) → {type, disposition}` | 3 类（phi_reflow/harmful/hallucination）规则核；phi_scan 运行时注入（v0.6 全集成） |

> stub（v0.6+）：internal-kb / ci-trigger / pm-bridge / vector-db。

---

## 4. model-router PolicyCore（5 层 gate · 护城河核心）

[mcp/model-router/policy.py](../../mcp/model-router/policy.py)，每次路由按序裁决，**任一不过 → deny（fail-closed）**：

| 层 | 检查 | 失败处置 |
|---|---|---|
| ① 脱敏标记 | 带 PHI 的体是否已脱敏（`desensitized==true`） | 未脱敏 L3/L4 → deny |
| ② allowlist 命中 | `model_id` 在 `MODEL_ALLOWLIST.json` 内 | 不在 → deny |
| ③ agent 角色 | 请求 `agent_role` ∈ 该模型 `allowed_agent_roles` | 越权 → deny |
| ④ 数据等级 | 请求 `data_level` ≤ 该模型 `allowed_data_levels` 上限 | 超级 → deny / 改路由敏感通道 |
| ⑤ 异构性 | （合规审查等场景）coder 模型 ≠ reviewer 模型厂商（`vendor_families.yml`） | 同源 → deny |

输出 `allowed_model_set` 后，**底座只在集合内按价/延迟/健康排序**。叠加 `limits.py`：per-token/per-model 限流 + 熔断（默认阈值 5）。

---

## 5. 数据模型

### 5.1 ClickHouse（已有 schema · 待入 compose）

**`_audit_log`**（[mcp/audit-log/sql/audit_log.sql](../../mcp/audit-log/)）— append-only · MergeTree · PARTITION BY month · **TTL 7y** · WORM（仅 INSERT，禁 ALTER/DELETE）：
```
event_id(UUID) ts actor_role actor_token action_type action_target
context_ctx context_lane result_status result_code
input_hash output_hash prev_hash current_hash row_id
```
→ 0 PHI：只存 action/result/哈希/占位符标签。`current_hash = SHA256(prev_hash ‖ canonical(event))`，daily verify。

**`_phi_lookup`**（[mcp/desensitize/sql/phi_lookup.sql](../../mcp/desensitize/)）— **TTL 6y(HIPAA)** · WORM：
```
map_id change_id key_id key_generation algorithm schema_version
nonce_b64 aad_sha256 ciphertext_b64 ciphertext_sha256
```
→ 仅 AES-GCM 信封，**无明文反查表**；解密需 desensitize + 受控授权。

### 5.2 继承自 new-api（fork 扩字段）
| 实体 | new-api 基线 | 我们加 |
|---|---|---|
| **channels（渠道）** | 多渠道/权重/单价/健康/亲和缓存 | `data_level`(承载上限) · `lane`(常规/敏感) · `region`(境内/境外) · `retention_policy` |
| **tokens（令牌）** | 配额/分组/模型限制 | `allowed_data_levels`（控合规）+ 复用配额（控成本） |
| **users/groups** | 登录/OIDC/passkey/分组 | 仅保留 OIDC+passkey；映射 Console 2 角色；关自助注册/社交登录 |
| **billing/quota** | 计费/额度 | 转**内部成本分摊 + 成本护栏**（服务划算） |

### 5.3 MODEL_ALLOWLIST.json（运行态 gate 数据）
`compliance-precheck` Skill（研发 Step 0）生成、签名，热加载进 model-router：
```jsonc
{ "change_id": "...", "models": [
  { "id": "qwen-max-2026", "vendor_family": "qwen", "deployment": "private://...",
    "allowed_agent_roles": ["coder","docs"], "allowed_data_levels": ["L1","L2","L3"], "rate_limit_qps": 5 } ]}
```

---

## 6. A0 只读聚合 API 后端（C9 · 契约 v0.7.0，后端待实现）

**契约是前后端唯一耦合点**（[types.ts](../../web/src/api/contract/types.ts) / [endpoints.ts](../../web/src/api/contract/endpoints.ts)），BE 照此实现，base `/api/v1`：

| 端点 | 方法 | 聚合来源 | 0-PHI 约束 |
|---|---|---|---|
| `/posture` | GET | router 健康 + audit 统计 → composite/compliance/security score + gates[] + alerts[] | `alerts[].payload` 恒 null |
| `/traffic?window=&ctx=` | GET | audit 聚合 → inbound{upstreams,gate,downstream} + outbound{built,gate} | `outbound.built:false` → FE 渲 🚧 |
| `/events?cat=&ctx=&limit=` | GET | audit 事件流 → ComplianceEvent(带 level) \| SecurityEvent(带 sec_type) | 安全事件 `payload` 恒 null |
| `/audit/{ref}` | GET | audit 单事件 → 血缘 nodes[] + hash(链校验) + details(KV) | details.v 仅占位符/哈希/聚合 |
| `/upstreams` | GET | new-api channels + audit → 健康 + `phi:"命中312/拦5"`(计数) | 聚合摘要串非原文 |
| `/cost?window=` | GET · **v0.7.0** | new-api 计费/quota + audit 聚合 → KPI/构成/趋势/省钱建议 | 全聚合数，天然 0 PHI |
| `/channels` | GET · **v0.7.0** | new-api channels → 比价（价/延迟/区域/权重/健康） | 聚合，无 PHI |
| `/config/{section}` | GET | 策略快照（10 section） | output/quota `built:false` |
| `/audit/export` | POST | 触发 AUDIT_BUNDLE 打包 | **唯一**落审计的写动作 |
| `/config/{section}/propose` | POST | 产 `approval_id`（不旁路 Hook） | **不直接改配置**，走审批流 |

**v0.7.0 成本端点类型**（[types.ts](../../web/src/api/contract/types.ts)）：
```ts
GET /cost?window=1h|24h|7d|month
  → CostResponse { window, kpi:CostKpi, by_lane:CostByDim[], by_model:CostByDim[], trend:number[], tips:CostTip[] }
    CostKpi   { month_cost, saved_vs_direct, saved_ratio, cache_hit_ratio, cache_saved, cap_day, cap_used, cap_left_ratio, normal_lane_ratio }
    CostByDim { name, color_token, pct, amount }      CostTip { tip, saving }
GET /channels → ChannelsResponse { channels: Channel[] }
    Channel { name, model, weight, unit_price, p95_ms, region, picked, status }
```
> 成本端点全为聚合数/分类标签，**天然 0 PHI**；后端从 new-api 计费/quota + channels + audit 聚合。

**后端实现红线**（[types.ts](../../web/src/api/contract/types.ts) 头注 + COMPLIANCE_TAG §8）：
- **字段白名单序列化**（不 dump 整对象）；安全事件 `payload` 恒 null；错误体 `{error:{code,msg}}` 不含版本/栈/路径。
- 服务端**也跑** `assertNoPhi` 等价校验（与 FE 同 [drill_api_phi_exfil.py](../../tests/red-team-drills/) 模式），出参前最后一道。
- 写口语义：`propose` 只入审批队列 → 审批通过后才走 PR/Hook 改配置；`export` 落审计 + 异步打包。

> **未实现**：拟 FastAPI 单服务，读 ClickHouse + 调 model-router/audit-log。Phase A 落地。

---

## 7. 脱敏与密钥（desensitize + KMS）

- **加密**：AES-256-GCM，AAD 绑定 5 字段（Algorithm/ChangeId/KeyId/MapId/schema_version）防错位重放；p99 0.02ms。
- **密钥**：v0.5 `FileKeyProvider`（`/data/medharness/keystore`，多代轮换）；云 KMS proxy-mode 留 v1.0。轮换：新代加密、旧代仅解密，`key_generation` 落 `_phi_lookup`。
- **反查**：`decrypt_mapping(map_id)` 仅在受控环境 + 三签授权；Console 内**永不**反查。

---

## 8. 划算：分级路由 + 渠道择优 + 缓存 + 护栏

- **双通道**：RouteDecision.lane 决定常规（境内低成本池扇出）/ 敏感（私有不出境）。
- **渠道择优**：复用 new-api 渠道加权（价/延迟/健康），**仅在 `allowed_model_set` 内**；provider 须有 no-training/no-retention/境内驻留条款方可入常规池。
- **缓存**：Redis 仅存脱敏体 + 严格 TTL + 租户隔离；命中也过 post-call gate。
- **护栏**：日成本上限 + per-user/model 限流 + 超额告警（复用 new-api quota + limits.py）。
- **省钱建议**：A0 `/config` + audit 聚合出"简单任务降到更省的小模型"等建议（绝不跨 lane/allowlist）。

---

## 9. fail-closed 与错误语义

| 场景 | 处置 |
|---|---|
| 任一闸门 fail/超时/不确定 | **默认拒** 或落敏感通道，绝不滑入常规通道 |
| ClickHouse 故障 | audit 切 FALLBACK（文件续链 + PID lock），服务不下线，恢复后 BACKFILL |
| provider 故障 | 重试/切换**限 allowed_model_set**，集合外网络层拦 |
| 雪崩 | 熔断（默认 5）+ 入站限流 |
| 网关自身故障 | 危险请求 fail-closed；网关服务保持可用（单实例健壮性，HA 留 v1.0） |

---

## 10. 后端落地清单（建/缺口）

| 项 | 状态 | 优先级 |
|---|---|---|
| 6 控制面服务内核 + 337 测试 + 4 红队 | ✅ | — |
| ClickHouse/_audit_log/_phi_lookup schema | ✅ 定义，🔴 未接客户端 | P0 |
| **fork new-api + relay 焊入 pre/post（§2）** | 🔴 | **P0** |
| **合规中间件 C2（内置 Go · §2.2）** | 🔴 | **P0** |
| **A0 API 后端 10 端点（含 /cost /channels · §6）** | 🔴 契约 v0.7.0 已定 | **P0** |
| ClickHouse/Redis/KMS 入 compose | 🔴 | P0 |
| outbound-safety 全集成 + 流式 SSE | 🟡 | P1 |
| channels/tokens 扩字段（数据等级/lane） | 🔴 | P1 |
| 云 KMS proxy / 多模态 PHI / 语义重放 | ⏭️ | v1.0 |

> P0 = Phase A，先把 §4 脊柱在 HTTP 边界焊死 + A0 通了 Console 才有真数据。
