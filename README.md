# MedHarness · 医疗大模型流量安全与合规网关

> 给医院、医疗信息化厂商和医疗 AI 团队用的**大模型统一出口**：
> 每一次模型调用先过患者敏感信息识别、脱敏、分级路由、出站检查和审计留痕，再转发给允许的模型。
>
> 开源 · 支持私有化/专有云部署 · 面向中国医疗数据合规场景
> （个人信息保护法 PIPL · 数据安全法 · 网络安全法/等保 · 健康医疗数据安全指南，兼顾 HIPAA）

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-CC_BY--SA_4.0-lightgrey.svg)](LICENSE-CC-BY-SA-4.0)
[![Status](https://img.shields.io/badge/Status-v1.0.0_stable-brightgreen.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-594_passed-brightgreen.svg)](#实测验证)
[![PHI Recall](https://img.shields.io/badge/PHI_recall-1.0_/_FP_0.09-brightgreen.svg)](#实测验证)
[![Container](https://img.shields.io/badge/container-13_images-brightgreen.svg)](#架构与部署)

---

> 说明：下文少量出现的 PHI 指患者健康医疗相关敏感信息，包括身份标识、就诊记录、检查检验、影像、诊断、用药等。

## 一句话：它是什么

HIS、EMR、CDR、互联网医院、随访系统、Dify/RAG/Agent，或者研发工具，只要把 `base_url` 指向 MedHarness，
每一次大模型调用都会先经过一条**强制合规闸门**：
识别患者敏感信息 → 脱敏 → 数据分级签名 → 模型白名单路由 → 提示注入扫描 → 出站安全检查 → 全量审计。
任一环节不确定或判定有风险，就直接拒绝，不连接上游模型。

它不是又一个通用大模型网关（LLM Gateway）。通用网关解决“接模型、限流、计费”，MedHarness 解决医疗场景里更关键的三件事：
**患者数据能不能出、能出给哪个模型、出了事能不能查清楚**。

```
  HIS · EMR · CDR · 互联网医院 · Dify · RAG · Agent · 研发工具
                     │   OpenAI / Claude 兼容协议 —— 改 base_url
                     ▼
        ┌──────────────────────────────────┐
        │        MedHarness 合规网关        │
        │  识别→脱敏→分级→路由→注入→[转发]→出站→审计 │
        └──────────────────────────────────┘
                     │   脱敏后 · 白名单内 · 全链路留痕
                     ▼
          合规可用的大模型（境内 / 私有 / 脱敏后受控调用）
```

---

## 这是给谁的

**适合**：正在或准备接入大模型的医院信息中心/医信科、数据中心、互联网医院、医联体/区域平台、
医疗 SaaS/AI 厂商、科研信息化团队。
典型场景包括智能问诊与分诊、病历结构化与质控、医学知识库 RAG、随访与客服、科研数据助手。
如果你的系统要在院内或专有云部署，且必须说清楚“患者数据有没有出院、有没有出境、谁访问过、出了事怎么追溯”，MedHarness 就是这个入口层。

**不适合**：没有患者数据/健康医疗数据的通用 SaaS、个人玩具项目。那些场景直接用通用模型网关就够了。

你大概率至少中了下面一条：

| 痛点 | 不管的后果 | MedHarness |
|---|---|---|
| 患者姓名、证件号、手机号、病历号、检查检验结果随模型输入（prompt）出网 | 个人信息保护、数据安全、委外处理和数据出境都说不清 | 入站强制识别 + 可逆脱敏，裸敏感信息进不了模型输入 |
| 模型和数据等级不匹配 | L3/L4 数据被路由到不该去的模型或区域 | 模型白名单 + 数据分级**零信任签名**，客户端不可自报等级 |
| 出了事无审计可查 | 等保、院内安全审计、客户安全评审要材料时拿不出来 | WORM + 哈希链审计血缘，按事件可追溯、可重放 |
| 多模型费用和配额不可控 | 项目上线后不知道钱花在哪个科室/应用/模型上 | 实时用量与成本聚合 + 配额强制 + 白名单内择优路由 |

---

## 凭什么不是"又一个通用大模型网关"

我们**不重造通用网关**。MedHarness 站在一个成熟的开源模型网关内核之上：
模型接入、令牌、用户、计费、OIDC、多渠道择优这些通用能力直接继承；
我们把主要工程投入放在医疗场景最难落地的合规控制面上。

通用大模型网关（one-api / LiteLLM / Higress AI 网关等）主要解决**路由 / 限流 / 计费 / 多模型接入**。
MedHarness 在同一条模型调用路径上，多了一层通用网关没有的**医疗数据安全与合规控制**：

| 能力 | 通用大模型网关 | MedHarness |
|---|:---:|:---:|
| 多 provider 路由 / 限流 / 计费 | ✅ | ✅（继承成熟网关底座） |
| 患者敏感信息识别 + 可逆脱敏（AES-256-GCM + AAD） | ❌ | ✅ |
| 数据分级**零信任签名**（客户端不可自报 L4） | ❌ | ✅ |
| 异构合规审查（防"自证清白"） | ❌ | ✅ |
| 出站敏感信息回流 / 幻觉医嘱拦截 | ❌ | ✅ |
| PIPL / 数据安全审计血缘（WORM · 6 年可重放，兼容 HIPAA 场景） | ❌ | ✅ |

对医疗信息化团队来说，这层决定的是：能不能上线、能不能过审、出问题能不能定位到责任链。

---

## §D.1 合规脊柱（核心机制）

每一次模型调用，都会在网关 `/v1/*` 入口被合规中间件拦截。
这个中间件不是旁路服务，而是焊在网关转发链路里：先检查，再决定能不能转发。

```
 client ─→ TokenAuth ─→ ① 敏感信息识别 ─→ ② 脱敏 ─→ ③ 数据分级签名（零信任）
                                                          │
        ⑥ 出站安全 ←── [ base relay 转发上游 ] ←── ⑤ 注入扫描 ←── ④ 模型白名单路由
              │
          审计双写（WORM + 哈希链）
```

不变量（任一不满足即拒）：

- **fail-closed（宁可拒绝，也不带病放行）**：任一闸门异常 → 通用 503；deny 时不连接上游模型。
- **零信任分级**：数据等级只由网关签发，model-router 只认签名结果；业务系统不能自己报“我是低敏数据”。
- **底座无自主路由权**：通用网关底座只能执行 MedHarness 给出的 `allowed_model_set`，不能自己跨白名单 fallback。
- **审计全量**：每次调用都写 `_audit_log`，不允许“先放行、后补记”。

附加防线：出站不仅检查患者敏感信息回流，还会对典型医疗幻觉做规则告警
（例如虚假安全承诺、武断确诊、擅自调整剂量、伪造权威来源）。

---

## 任何客户端，一个端点

合规闸门挂在 `/v1/*` 整组上，并同时兼容 OpenAI、Claude、Responses 三类常见协议。
因此，不管是院内业务系统、医疗 AI 应用，还是研发工具，只要支持配置模型服务地址，改 `base_url` 就能接入：

| 客户端 | 指向端点 | 协议 |
|---|---|---|
| HIS/EMR/CDR 对接服务、互联网医院、Dify、RAG、Agent | `/v1/chat/completions` · `/v1/embeddings` | OpenAI |
| **Claude Code**（研发医疗系统 / 碰医疗数据） | `/v1/messages` | Anthropic Messages |
| **Codex CLI**（研发医疗系统 / 碰医疗数据） | `/v1/responses` | OpenAI Responses |
| Cursor / 其它工具 | `/v1/chat/completions` | OpenAI |

> **开发期也是数据流量来源**：研发同事用 Claude Code / Codex 写医疗系统时，也可以让工具走网关令牌和同一条合规闸门。
> 这样开发期 prompt、测试数据、生产流量都有同一套审计口径，不需要给每个 IDE 单独写 Hook。
>
> ⚠️ **配置不等于强制**：要真正堵住绕过，需要配合网络出口管控
> （开发机、CI、应用服务器只能经网关访问大模型）。
> 网关提供统一闸门；强制性来自网络层。另一个好处是开发者手里不再持有真实模型厂商 key，
> 只有可吊销、带配额、可审计的网关令牌。

---

## 控制台（七屏）

给系统管理员、研发负责人、合规/安全人员看的运维控制台。
浏览器登录即用（自建 React 控制台，经 A0 控制面 BFF 读数，全程不展示患者原始敏感信息）：

| 屏 | 看什么 |
|---|---|
| 总览 | 四目标实时态势（安全·成本可控·可审计·稳定，真实聚合）+ 六道闸门 + 月度小结 |
| 流量监控 | 实时流量桑基图 + 双色事件流 |
| 合规与报表 | 可检索合规事件 + 血缘图 + 哈希链 |
| 用量与成本 | 真实开销聚合（按模型 / 通道 / 趋势）+ 配额护栏 |
| 接入 | 渠道 / 接入令牌 / 用户与分组**集中管理**（建·改·停·删）· 医疗模型目录一键预填 |
| 策略 | 配置 / 策略 + 变更先预览再审批 |
| 系统 | 系统与上游健康 |

> 角色分离：**系统管理员**管账号、渠道、令牌；**研发负责人/合规人员**看态势、审计和报表。
> 控制台不反查患者原文，患者原始敏感信息在任何屏都不展示。

---

## 架构与部署

面向院内机房、专有云或医疗企业私有化部署。单机、双网隔离，约 4-5GB 内存 / 4 vCPU 一台 host 可运行：

```
┌──────────────────────────────────────────────────────────────┐
│  Host（院内/专有云 · 单机 · 约 4-5GB / 4 vCPU）                │
│                                                               │
│  ┌─────────────┐                                              │
│  │   nginx     │  ← DMZ · 仅放行 /v1/* + /api/v1/* + /health   │
│  │  (TLS 443)  │     TLS 1.2/1.3 · HSTS · 杀裸 /api/route      │
│  └──────┬──────┘                                              │
│         │                                                     │
│  ┌──────┴────────────────────────────────────────────────┐   │
│  │  medharness_internal（internal: true · 不暴露 host）   │   │
│  │                                                        │   │
│  │  合规网关（§D.1 脊柱）         a0-api（控制面 BFF）    │   │
│  │  phi-detector  desensitize  model-router  injection   │   │
│  │  outbound-safety  audit-log                           │   │
│  │  internal-kb  vector-db  ci-trigger  pm-bridge        │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
│  状态：ClickHouse（审计 WORM）· Redis · KMS                   │
│  真实模型 key 只在网关渠道配置，业务系统只拿网关令牌            │
└──────────────────────────────────────────────────────────────┘
```

13 个容器镜像 = 11 个合规 MCP（phi-detector / desensitize / model-router / prompt-injection-scan /
outbound-safety / audit-log / internal-kb / vector-db / ci-trigger / pm-bridge / a0-api）+ 网关 + nginx。
multi-stage、非 root、Trivy 0 高危。

---

## 快速开始

### 路径 A · 全栈起栈 + 控制台（生产/预生产环境）

```bash
git clone https://github.com/charliehzm/medharness.git && cd medharness

# 1. 生成 TLS cert（默认 self-signed · BYO 见 ADR-06）
bash scripts/gen-tls.sh

# 2. 配置 env（复制模板后填密钥）
cp deploy/.env.production.example deploy/.env.production
#   必填：MODEL_ROUTER_TIER_SECRET（网关↔model-router 同值，分级签名密钥）
#         A0_SESSION_SECRET（≥32B，控制台会话 token 签名）
#   选填：NEW_API_ADMIN_TOKEN / NEW_API_ADMIN_USER_ID（启用控制台用户管理写口；
#         为网关 root 的 access_token + id，仅注入 a0-api 容器内网，绝不出 DMZ）

# 3. 一键构建并启动全栈（13 image）
docker compose -f deploy/docker-compose.prod.yml \
               --env-file deploy/.env.production up -d --build

# 4. 健康检查 + 登录控制台
docker compose -f deploy/docker-compose.prod.yml ps     # 全 healthy
curl -k https://localhost/health                         # DMZ 健康
#   浏览器开 https://localhost/ → 登录（网关 root：admin / 首启所设密码）
```

> **部署后校验**：登录后「总览」六道闸门显示「已上线」；「用量与成本」显示真实聚合开销（无流量则 $0.00）；
> 「接入 → 用户与分组」（系统管理员）可建 / 改 / 停用账号。控制台全程不展示患者原文。

### 路径 B · 只想先看它能不能跑（开发机）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m pytest tests/        # 594 passed（活栈层需先起栈）
bash tests/red-team-drills/run_all.sh    # 4 红队演练 + 5 CI gates
bash scripts/e2e_full.sh                 # 活栈 7 层 E2E 全绿
```

---

## 四目标 × 怎么兑现

| 目标 | 兑现 |
|---|---|
| 🔒 **安全** | 入站患者敏感信息 0 裸出（recall 1.0）· 出站敏感信息回流 / 幻觉拦截 · 注入防御 11/11 |
| 💰 **成本可控** | 多渠道择优 + 缓存 + 实时成本可视 + 配额护栏 |
| 📋 **可审计** | 数据分级零信任 · 异构审查 · WORM 审计血缘 6 年可重放 |
| 🟢 **稳定** | 失败默认拒绝（fail-closed）· 多渠道冗余 · 594 测试 + 活栈 7 层 E2E + 跨浏览器 UI 视觉回归 |

---

## 实测验证

```bash
.venv/bin/ruff check .                        # clean
.venv/bin/python -m pytest tests/              # 594 passed
bash tests/red-team-drills/run_all.sh          # 4 drills + 5 gates 全过
bash scripts/e2e_full.sh                       # 活栈 7 层（离线/网关/数据/闭环/失败闭合/冒烟/UI）全绿
```

**红队 CI**（`.github/workflows/compliance.yml` · 每周一 09:00 CST · 失败自动开 issue · 90-day artifact）：

| Drill | Threshold | 实测 |
|---|---|---|
| drill 1 PHI recall | ≥ 92% | 1.0 |
| drill 1 FP rate | ≤ 15% | 0.09 |
| drill 2 router bypass | 11/11 deny | 11/11 |
| drill 3 audit chain | intact + tampered detected | 全过 |
| drill 4 injection block_rate | ≥ 95% | 1.0 |
| drill 4 injection fp_rate | ≤ 10% | 0.0 |

**Docker build CI**（`.github/workflows/docker-build.yml` · 每周一 10:00 CST · Trivy scan）：生产 MCP image < 500MB、Trivy HIGH+CRITICAL = 0。

---

## 社区版 vs 商业版

开放核心（open-core）：**网关 + 控制台 + 11 MCP 全开源**；差异化能力（需真实数据 / 训练 / 托管）是商业版。
社区版对未建能力一律「即将推出」诚实标注，**绝不冒充已建**。

| 能力 | 社区版（Apache 2.0） | 商业版 |
|---|:---:|:---:|
| 合规网关（§D.1）+ 控制台 + 11 MCP（容器化） | ✅ | ✅ |
| 4 红队 drill + 5 CI gates | ✅ | ✅ + Slack / PagerDuty |
| 31 fields.yml | ✅ 通用 | ✅ + 客户化字段 |
| 训练好的中文医疗 phi-detector 模型（社区为规则 + Presidio） | ❌ | ✅ |
| 出站幻觉**训练版分类器**（社区为规则启发式） | ❌ | ✅ |
| 成本**治理智能**（较直连节省 / 缓存 ROI / 优化建议 / 日预算硬上限） | ❌ | ✅ |
| 托管 MCP 集群（KMS / WORM）+ 分布式向量检索 + 训练 reranker | ❌ | ✅ |
| OIDC / 多租户 / 计费 / 24x7 合规 SLA / 1 对 1 督导 | ❌ | ✅ |

**License 永久承诺**：已发布的社区版组件，license **永久** Apache 2.0 / CC BY-SA 4.0。不会效仿 MongoDB / Elastic 改 SSPL / BSL。

详见 [docs/community-vs-commercial.md](docs/community-vs-commercial.md)。

---

## 参与 / 社区

| 我想... | 路径 |
|---|---|
| 提问 / 案例分享 | [GitHub Discussions](https://github.com/charliehzm/medharness/discussions)（推荐 · 可被搜索） |
| 报 bug / 提 feature | [GitHub Issues](https://github.com/charliehzm/medharness/issues/new/choose) |
| 报合规漏洞 / 患者敏感信息泄漏 | [GitHub Security Advisory](https://github.com/charliehzm/medharness/security/advisories/new)（私密 · **勿在 public issue 提**） |
| 早期客户接洽 / 深度合规咨询 | 微信 `supernera`（maintainer 直联 · 工作日 24h） |
| 贡献代码 | [CONTRIBUTING.md](CONTRIBUTING.md) → fork → PR |

**Star 这个仓库**如果你认同这个方向。Star 会帮助我们判断社区版能力的优先级。

---

## 上游致谢 · License · 引用

- **网关底座**：MedHarness 的合规层焊在一个成熟的开源网关内核之上；上游项目的版权、品牌与归属完整保留于 `vendor/` 内其自带的 LICENSE 与 README。
- 代码（MedHarness 自有合规层）：[Apache 2.0](LICENSE)
- 文档：[CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0)
- 安全披露：[SECURITY.md](SECURITY.md) · 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

```bibtex
@software{medharness2026,
  title  = {MedHarness: A Compliance Gateway for Medical LLM Traffic},
  author = {MedHarness Maintainers},
  year   = {2026},
  url    = {https://github.com/charliehzm/medharness},
  license = {Apache-2.0}
}
```

---

## 附：开发期合规研发体系（方法论）

MedHarness 起源于一套"AI Coding 合规研发体系"——12+5 步双通道 SOP、合规 Skill、异构 sub-agent、6 层治理（见 [`CLAUDE.md`](CLAUDE.md)）。
**合规强制现已归网关**（见上「任何客户端，一个端点」）；这套方法论作为"如何组织 AI 写医疗代码的流程"保留，
详见 [研发交付SOP-v2.md](研发交付SOP-v2.md)。

> 成为医疗机构接入大模型的安全与合规底座，让每一次医疗 AI 调用都可控、可审计、可追溯、可重放。
