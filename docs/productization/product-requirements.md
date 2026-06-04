# MedHarness 产品需求文档（PRD · 统一）

> **状态**：DRAFT（草稿，待技委 + 合规委 + 法务会签）
> **产品**：**MedHarness** —— 医疗大模型流量网关。一句话：**让医疗团队的每一次大模型调用都安全、划算、可审计、稳定。**
> **为什么有这份文档**：此前各 change 的 `proposal.md` 各自为政，**缺一份跨版本的统一需求源**。本 PRD 即此基准。
> **配套**：产品形态见 [console-product-design.md](console-product-design.md)；架构见 [unified-gateway.md](../architecture/unified-gateway.md) + 重设计 RFC [gateway-substrate-selection.md](../architecture/gateway-substrate-selection.md)。
> **四大目标**：**安全 · 划算 · 审计 · 稳定**。注：「闭环」只是治理/运营方式，**不是产品目标**。

---

## 1. 背景与问题

医疗数据 SaaS / 互联网医院团队（≤30 人）已普遍用 Claude Code / Codex 写代码、用 Dify / ComfyUI 跑生产工作流。问题：

- **数据出境违规**：工程师把含姓名/身份证/病案号的样例粘进 prompt，走了境外公共 API → 触犯 HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南，最高可罚全球营业额 4%。
- **生产同样有险**：Dify/ComfyUI 等生产工作流调大模型，泄露面与开发期对称，且**出站**方向新增风险（模型回吐 PHI / 幻觉医嘱 / 有害输出）。
- **成本失控**：全量走 frontier 大模型既贵又没必要；缺乏分级与护栏。
- **查不清**：出事无法快速举证、应对监管。
- **怕拖垮生产**：网关一旦进入所有 LLM 调用的关键路径，它自己不能成为新的故障点。

MedHarness 把开发态 + 生产态的所有大模型流量**收口为单一受控入口**，用一套闸门同时解决以上问题。

> 定位演进：v0.5 定位「医疗 SaaS 内部 AI Coding 合规体系」（安全+审计强、划算仅 RFC、稳定明确范围外）→ 本次升级为通用「医疗大模型流量网关」，**把划算提为承诺目标、把稳定提为一等目标**，底座按 RFC 走 OSS 深度 fork。

---

## 2. 目标用户（2 个 Console 角色）

| 角色 | 画像 | 核心诉求 |
|---|---|---|
| **研发负责人**（买单+主用+审批，吸收 CTO+合规官） | 小公司技术 1 号位 | 安全不出事、成本可控、检查能交差、别拖垮生产 |
| **系统管理员**（运维+接入） | 兼职运维，无专职 SRE | 装得起、接得上、看得懂健康、低危配置自己改 |

- **工程师 = 终端使用者，不进 Console**：仅 base_url + 个人令牌，全程无感。
- **外部合规顾问 / 法务**：仅最高危变更（PHI 字段、保留期）会签。
- 角色精简理由：≤30 人公司既无独立 SecOps，也很少有独立于技术负责人的专职合规官——故 2 角色（详见 [console-product-design.md §2](console-product-design.md)）。

---

## 3. 四大目标（可度量）

> 现状基于真实仓库：✅ 已扎实 / 🟡 部分或规划 / ❌ 缺口。

### G1 · 安全（合规 + 防护）— ✅ 强
| 指标 | 目标 | 现状 |
|---|---|---|
| PHI 检测 | recall ≥ 0.92 / FP ≤ 15% | ✅ recall 1.0 / FP 0.09（220 合成样本） |
| 数据出境违规 | **0 次** | ✅ 越权 11/11 全拦 |
| 模型准入 | 100% 经 allowlist | ✅ model-router 5 层 gate |
| 注入阻断率 | ≥ 0.95 | ✅ 1.0（25 case） |
| 出站响应安全 | PHI 回流/有害/幻觉医嘱拦截 | 🟡 规划新增，stub |

### G2 · 划算（成本）— 🟡 RFC→本次转承诺
| 指标 | 目标 | 现状 |
|---|---|---|
| 较全量直连 frontier 节省 | ≥ 30% | 🟡 分级路由仅 RFC（§C） |
| 低敏流量走境内低成本池占比 | 可视可调 | 🟡 clean/PHI 双通道已定义未落地 |
| 缓存命中降本 | 启用并可见 | 🟡 仅约定 cache 在 gate 之后 |
| 多渠道择优 | 同模型按价/延迟/健康自动选 | 🟡 复用 new-api 渠道加权（本次落地） |
| 成本护栏 | 日成本上限 + 限流 + 超额告警 | 🟡 限流在出站段 |

> 出处：[gateway-substrate-selection.md §C](../architecture/gateway-substrate-selection.md)「脱敏是桥——把贵且受限的流量转成低成本且可广发的流量」。

### G3 · 审计（可追溯）— ✅ 最完整
| 指标 | 目标 | 现状 |
|---|---|---|
| 审计覆盖 | 每次调用 100% 落审计 | ✅ audit-log |
| 防篡改 | 哈希链 + WORM，daily verify | ✅ 三层（ClickHouse append-only + chattr +a + SHA-256） |
| 审计内容 | **0 PHI** | ✅ 仅占位符/哈希/聚合 |
| 可重放 | 6 年 | ✅（语义重放留后续） |
| 监管应对包 | ≤ 4 小时交付 | ✅ 4h 演练 |

### G4 · 稳定（可用性）— ❌ 真缺口，本次提为一等目标（单实例尺度）
| 指标 | 目标（单实例） | 现状 |
|---|---|---|
| 网关附加延迟 | 非流式 p95≤80ms/p99≤150ms；流式 TTFT p95≤50ms | 🟡 router <5ms，端到端预算见 RFC §G.2 |
| provider 故障 | 自动重试 + 渠道切换（限 allowlist 内） | 🟡 复用 new-api 渠道重试 |
| 防雪崩 | 熔断（默认 5）+ 限流 | 🟡 阈值/入站限流待定 |
| 故障降级 | fail-closed 拒危险请求，**网关服务保持可用** | 🟡 fail-closed 有，服务级降级未设计 |
| 审计不丢 | ClickHouse 故障 → 文件 fallback 续链 | ✅ fallback_writer + PID lock |
| 运维 | 健康检查 + 一键备份/恢复/升级 | ✅ compose healthcheck + T11/T12 |
| **HA / 多副本 / 自动 failover** | **不在本期**，留 v1.0 | ❌ v0.5 proposal §4 明确范围外 |

> **诚实声明**：v0.5 proposal §4 明确排除 HA/多副本/监控栈，定位「PoC-grade not SLA-grade」。本次「稳定」**指单实例健壮性**（不拖垮生产、优雅降级、审计不丢、性能有界），**不等于 HA**。须在合同/客户沟通讲清，避免误期望。

---

## 4. 范围

**范围内（MVP，按四目标）**
- 安全：入站 4 闸 + 出站响应安全检查。
- 划算：数据分级双通道 + 多渠道择优 + 缓存 + 成本护栏 + 成本看板。
- 审计：ClickHouse + 哈希链 + WORM + 一键监管应对包。
- 稳定：性能预算 + provider 重试/切换 + 熔断/限流 + fail-closed 不下线 + 审计不丢 + 健康/备份/升级。
- 接入：base_url 零改造（Claude Code/Codex/Dify/ComfyUI）+ 统一控制台。

**范围外（明确告知客户）**：❌ HA/多副本/自动 failover（→v1.0）· ❌ k8s/helm · ❌ Prometheus/Grafana 全栈监控 · ❌ 多租户 · ❌ 托管 SaaS/24x7 SLA。

**fork 移除项（合规硬要求，不是"不做"而是"主动裁掉"）**：本产品 fork new-api 后**必须移除/硬禁用**其面向"对公众转售 API"的能力——❌ 自助注册 · ❌ 对外支付(Stripe/EPay/Creem/Waffo) · ❌ 订阅售卖 · ❌ 兑换码 · ❌ 充值 · ❌ 钱包 · ❌ 签到 · ❌ 邀请返利 · ❌ 对外定价页 · ❌ 社交登录(Discord/LinuxDO/Telegram)。理由：企业受控内部网关不对公众转售，与 [gateway-substrate-selection.md §F](../architecture/gateway-substrate-selection.md) 一致，且这些是攻击面 + 合规风险。**保留** OIDC/passkey 企业登录 + 内部 quota/billing（做成本分摊，服务 G2）。

---

## 5. 功能需求（按四目标 + fork 底盘）

> 本产品 = new-api 深度 fork，天生继承其全功能面；下列 FR 在「继承基线」之上定义。完整继承/处置见 [console-product-design.md §11](console-product-design.md)。

**FR-F fork 继承与裁剪（底盘）**
- FR-F1 **继承**：relay 转发/channels 渠道/users·groups/OIDC·passkey/tokens/playground/system-settings/setup/多模态/**Codex 集成** 直接复用，不重造。
- FR-F2 **复用内部能力**：复用 new-api 的 quota/billing 做**内部成本分摊 + 成本护栏**（服务 G2）；复用 dashboard/usage-logs/perf_metrics 作可观测底座（叠加合规/安全/成本维度）。
- FR-F3 **移除转售**：fork 时移除/硬禁用 自助注册/对外支付/订阅售卖/兑换码/充值/钱包/签到/邀请/对外定价/社交登录（见 §4 fork 移除项）。验收：这些路由/页面不可达、无后端端点暴露。
- FR-F4 **认证收敛**：仅保留 OIDC + passkey 企业登录。
- FR-F5 **fork 维护**：移除优先用"禁用开关 + 路由隐藏"而非大改源码，降低 rebase 冲突；每次上游 rebase 后跑红队 drill + 回归。

**G1 安全**：FR-S1 入站 PHI 检测（规则优先 inline、重 NLP 异步）· FR-S2 脱敏（AES-256-GCM 可逆 + KMS）· FR-S3 模型准入（allowlist+分级）· FR-S4 注入防御（5 类，不回显 payload）· FR-S5 出站响应安全（PHI 回流/有害/幻觉，规划）。

**G2 划算**：FR-C1 数据分级双通道（低敏→境内低成本池 / 高敏→私有不出境）· FR-C2 多渠道择优 · FR-C3 缓存降本 · FR-C4 成本护栏（日上限+限流+告警）· FR-C5 成本看板（按通道/模型/上游、省比、趋势、省钱建议）。

**G3 审计**：FR-A1 全量审计 0 PHI · FR-A2 防篡改（哈希链+WORM+daily verify）· FR-A3 检索（时间/用户脱敏/模型/通道/事件）· FR-A4 监管应对包一键导出（含哈希链校验，≤4h）。

**G4 稳定**：FR-St1 性能预算守护 · FR-St2 provider 重试+渠道切换（限 allowlist）· FR-St3 熔断+限流防雪崩 · FR-St4 故障降级（fail-closed 不下线；ClickHouse 故障→审计 fallback）· FR-St5 运维（健康检查/备份/恢复/升级/离线包）。

---

## 6. 非功能需求
- **性能**（网关附加，不含 provider 推理）：入站检查 p95≤35ms/p99≤80ms；非流式 total p95≤80ms/p99≤150ms；流式 TTFT p95≤50ms/p99≤100ms（见 RFC §G.2）。
- **稳定**：单实例下故障不致审计丢失、不致服务整体不可用；危险请求 fail-closed。
- **安全基线**：fail-closed、egress allowlist、provider no-retention/no-training、缓存/日志 0 PHI、不放第三方聚合器、请求体大小限制。
- **部署**：单主机 docker-compose（new-api fork + ClickHouse 单节点 + Redis + KMS）；最低资源待 POC 校准（建议 ≥4 vCPU/8GB/50GB）。

---

## 7. 成功指标
- 北极星：**0 次 PHI 出境违规** + **较直连节省 ≥30%** + **监管包 ≤4h 交付** + **网关致生产不可用 0 次**。
- 护栏：注入阻断率 ≥0.95、审计 daily verify 100% 通过、网关附加延迟不超预算。

---

## 8. 约束
- 客户本地部署；不接第三方聚合器；敏感通道不出境。
- 底座**锁定 new-api 深度 fork**（maintainer r4 裁决）；AGPL §13 由**商业授权兜底**（向 new-api 取得商业许可，解除 copyleft / 分发义务）。详见 [gateway-substrate-selection.md r4](../architecture/gateway-substrate-selection.md)。
- License：产品 Apache 2.0 / 文档 CC BY-SA 4.0。一切 LLM 调用经 model-router；一切调用全量落审计。

---

## 9. 风险
| # | 风险 | 等级 | 对冲 |
|---|---|---|---|
| 1 | 底座 license（new-api AGPL） | 🟢 已解 | r4 锁定 new-api 深度 fork；**完全授权已获（2026-05-31）** 解 AGPL，不再回退 one-api |
| 2 | **稳定缺口**：单实例无 HA，客户误以为 SLA-grade | 🟠 | 合同/沟通明确「单实例非 HA，HA 留 v1.0」+ 做足单实例健壮性 |
| 3 | 低成本池模型质量/可用性不足 | 🟡 | 多渠道择优 + 按需升回 frontier；成本可见 |
| 4 | fork 维护：上游活跃 → rebase 成本 | 🟠 | 集中改动面；每次 rebase 跑红队 drill + 回归 |
| 5 | 出站扫描延迟 / 幻觉医嘱误报 | 🟡 | PHI lane 先缓冲再放行；误报阈值可调 |
| 6 | 脱敏召回非 100%，干净流量误放残留 PHI | 🟠 | clean lane 限境内 + 出站二次扫描 + 默认拒（fail-closed） |

---

## 10. 里程碑
| 阶段 | 内容 |
|---|---|
| **本期（重设计 MVP）** | 四目标单实例落地：安全 4+1 闸、划算双通道+护栏+看板、审计全链、稳定单实例健壮性 |
| **v1.0 / 商业版** | HA 多副本 + 自动 failover、全栈监控、多租户、托管 SaaS/24x7 SLA、语义重放、云 KMS proxy-mode |

---

## 附：文档关系
- 本 PRD = 统一需求源；各 change 的 `proposal.md` 应回指本文的 G1–G4 与 FR 编号。
- 产品形态 [console-product-design.md](console-product-design.md)；架构 [unified-gateway.md](../architecture/unified-gateway.md) + [gateway-substrate-selection.md](../architecture/gateway-substrate-selection.md)。
- 医疗模型选型/接入（FR-S3 准入 + FR-C1/C2 分级双通道·多渠道的落地清单）：[medical-model-catalog.md](medical-model-catalog.md)。
- v0.6（feat-v0.6-bidirectional-console）能力并入本重设计。
