# MedHarness 后端设计

> **状态**：**定稿 v1（实现基线）** · 异构闸门 WAIVED（待 B1 代码 + r3）。**已建** = mcp/ 6 服务 + 契约；**待建** = 网关焊接(C1/C2) + A0 后端(C9) + ClickHouse/Redis/KMS。
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
// new-api fork · relay 内置中间件（伪码 · 详见 ADR-18）
func ComplianceRelay(c *gin.Context) {
    body := readBody(c)
    decision := gate.PreCall(body)              // ① HTTP→C3-C6，阻塞；中间件签发签名 RouteDecision
    audit.Log("pre-call", decision.AuditLabels) // 不变量⑤：外呼前写（双写之一·Codex L2）
    if decision.Action == "deny" {              // 不变量①：deny 即静默
        c.JSON(deny);  return                   // 不外呼/不写 cache/不落上游日志
    }
    // 不变量②③：底座先 Verify(decision.Sig)，只在 allowed_model_set 内扇出，忽略客户端 model_id
    resp := relayWithDecision(c, decision)       // ②cache(仅脱敏体) ③retry(限set) ④dispatch ⑤log
    safe := gate.PostCall(resp, decision)        // ⑥ outbound-safety
    audit.Log("complete", safe.AuditLabels)      // 双写之二（外呼后）
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

> **Codex B2/B3**：当前 `policy.py` 的 RouteDecision 仅 `decision/reason/layer_failed`，**未**输出 `allowed_model_set`/`lane`/`max_data_level`；Phase A 必须按 [ADR-18 §2](../architecture/ADR-18-gateway-control-plane.md) 扩 PolicyCore + 中间件 **HMAC 签名**，且**拒收客户端自报分级**（B3）。
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

> **Codex B3/H1/H2**：分级（`data_level`/`desensitized`/`lane`）**只由中间件在 ①② 后写入**，PolicyCore 拒收客户端自报（[ADR-18 §3](../architecture/ADR-18-gateway-control-plane.md)）；`level_exceeds` 可降敏时返回 `action:reroute`（lane=sensitive 重算 set）而非纯 deny（H1）；新增**层⑥ lane×region 校验**（allowlist 加 `region/egress_zone`，H2）。

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
> **Codex B5（管理面 0-PHI）✅ 契约 v0.7.1 已落**：接入屏的**读**经 A0 **管理只读代理** `GET /admin/{users|tokens|channels}`（不直调 new-api，过 `assertNoPhi`）；类型 [types.ts](../../web/src/api/contract/types.ts) `Admin{User,Token,Channel}`，fixtures 实测 0-PHI。**写**仍直调 new-api 但走审批（不经 A0）。**字段白名单**（new-api OSS schema → 只回安全列）：
>
> | 实体 | 只回 | **禁（PII / 密钥）** |
> |---|---|---|
> | user | id 哈希 · role · status · group · quota/used_quota · console_role | username · **display_name** · **email** · github/wechat/telegram_id · access_token · password · verification_code |
> | token | id 哈希 · name(标签) · status · remain/used_quota · allowed_data_levels | **key（明文密钥）** |
> | channel | id 哈希 · name · type · status · weight · region · lane · models | **key · base_url（含密钥）** |
>
> ⏳ BE-6b 实现时**核对 fork 实际字段集**（防 new-api 当前版多字段）。
> **Codex L5**：A0 聚合实现**禁 SELECT 非白名单列**，禁 join 含原文的 new-api 日志表。

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
| 任一闸门 fail/超时/**不确定** | **不确定 = deny**（Codex M5）；仅「已脱敏但 lane 模糊」可落敏感通道，绝不滑入常规 |
| ClickHouse 故障 | audit 切 FALLBACK（文件续链 + PID lock），服务不下线，恢复后 BACKFILL |
| **审计写不可用**（FALLBACK 满 / BACKFILL 阻塞） | **= deny**（审计不可用不得放行，Codex H5）；BACKFILL 与实时写分离 + 异步队列满则 deny |
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
> **Codex r1 门禁补充**：B4 fork 延迟 POC（p50/p95/p99）+ H7 出站最小 B1 焊 ⑥ + L4 BACKFILL 后全链 verify 自动化测试 + 禁用清单集成测试（[ADR-18 §5](../architecture/ADR-18-gateway-control-plane.md)）—— 均 Phase A 验收项。详见 [复审处置](REVIEW-r1-codex.md)。

> **B4 延迟实测（2026-05-31 · 已 de-risk）**：phi-detector v3 inline 用 `RegexOnlyNlpEngine`（故意不装 spaCy 重模型）= §G.2「inline 仅 rule-first」已落代码；实测 `detect_v3` **p50 0.20 / p95 0.22 / p99 0.29ms**（194 字符多 PHI 样本）。全 inline 链（phi 0.22 + desens 0.02 + router <5 + inj-regex）≈ **<6ms**，远低于 35ms 预算 → fork POC 是**确认非发现**（仅余 Go 中间件一跳 + new-api relay 小增量）。
> **但暴露 cost×覆盖取舍**：regex-only inline **漏检 CN_NAME / MRN / 生物标识**（需 NLP 模型）。**✅ 采 Option B（[ADR-18 §3.1](../architecture/ADR-18-gateway-control-plane.md) 定论 2026-05-31）**：regex inline（快）+ **重 NLP 异步/抽样** + **L3+ 或含姓名/MRN 嫌疑内容默认落敏感通道（保守 fail-closed）**——不为省延迟在 inline 装 NLP（破预算风险）；0-PHI 真正靠**脱敏 + 后端字段白名单**，非 inline regex 全检（呼应 H3）。硬验收见 ADR-18 §3.1（「中文名+诊断码、inline 未命中名字」→ 落敏感不出境）。
