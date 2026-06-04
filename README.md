# MedHarness · 医疗大模型合规网关

> 在一个成熟的开源网关内核之上，焊一层**医疗合规脊柱**——
> 让医疗机构所有大模型流量：**PHI 不外泄 · 模型走白名单 · 全量可审计 · 成本可控**。
>
> 开源 · 私有化部署 · HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南 四合规

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-CC_BY--SA_4.0-lightgrey.svg)](LICENSE-CC-BY-SA-4.0)
[![Status](https://img.shields.io/badge/Status-v1.0.0_stable-brightgreen.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-594_passed-brightgreen.svg)](#实测验证)
[![PHI Recall](https://img.shields.io/badge/PHI_recall-1.0_/_FP_0.09-brightgreen.svg)](#实测验证)
[![Container](https://img.shields.io/badge/container-13_images-brightgreen.svg)](#架构与部署)

---

## 一句话：它是什么

你的业务系统 / Dify / RAG / Agent，甚至研发用的 **Claude Code、Codex**，只要把 `base_url` 指向 MedHarness，
每一次大模型调用都会被一条**强制闸门**拦下：扫 PHI → 脱敏 → 数据分级签名 → 模型白名单路由 → 注入扫描 → 出站安全 → 全量审计。
漏一层、下一层挡；任一层判危，**直接 fail-closed，0 上游连接**。

它不是又一个 LLM 网关。它是**专门给医疗场景**的那一层合规脊柱，焊在一个能接 40+ 模型厂商的成熟底座上。

```
  业务后端 · Dify · RAG · Agent · Claude Code · Codex
                     │   OpenAI / Claude 兼容 —— 改个 base_url
                     ▼
        ┌──────────────────────────────────┐
        │   MedHarness 网关  ·  §D.1 脊柱   │
        │  PHI→脱敏→签级→路由→注入→[转发]→出站→审计 │
        └──────────────────────────────────┘
                     │   脱敏后 · 白名单内 · 全程留痕
                     ▼
          合规的大模型（境内 / 私有 / 脱敏后出境）
```

---

## 这是给谁的

**适合**：正在或准备上大模型应用的医疗数据公司 / 医院信息科 / 医疗 SaaS——
智能问诊与分诊、病历结构化与质控、医学知识库 RAG、随访与客服 bot、科研数据助手。
团队不大（≤30 人）、要私有化、过不了等保 / HIPAA 审计就上不了线。

**不适合**：通用 SaaS（无 PHI，直接用通用网关即可）、个人玩家（这套偏重）。

你大概率至少中了下面一条：

| 痛点 | 不管的后果 | MedHarness |
|---|---|---|
| PHI 随 prompt 出境 | 违反 HIPAA + PIPL，可罚到全球营业额 4% | 入站强制扫描 + 脱敏，裸 PHI 进不了 prompt |
| 调到不合规 / 境外模型 | 数据出境违规 | 模型白名单 + 数据分级**零信任签名**，客户端不可自报 |
| 出了事无审计可查 | 监管要 6 年可追溯，拿不出来 | WORM + 哈希链审计血缘，4 小时可重放 |
| token 成本不可控 | 月底账单爆炸、不知道钱花哪 | 实时用量 / 成本聚合 + 配额强制 + 智能路由省钱 |

---

## 凭什么不是"又一个 LLM 网关"

我们**不重造网关**。MedHarness 站在一个成熟的开源网关内核之上——
直接继承接 40+ 模型厂商、用户 / 令牌 / 计费、OIDC、多渠道择优的能力，只把精力投在医疗合规这一层。

通用 LLM 网关（one-api / LiteLLM / Higress AI 网关 等）解决的是**路由 / 限流 / 计费**。
MedHarness 在**同一条数据路径**上，多焊了一层通用网关没有的**医疗合规脊柱**：

| 能力 | 通用 LLM 网关 | MedHarness |
|---|:---:|:---:|
| 多 provider 路由 / 限流 / 计费 | ✅ | ✅（继承成熟网关底座） |
| PHI 检测 + 可逆脱敏（AES-256-GCM + AAD） | ❌ | ✅ |
| 数据分级**零信任签名**（客户端不可自报 L4） | ❌ | ✅ |
| 异构合规审查（防"自证清白"） | ❌ | ✅ |
| 出站 PHI 回流 / 幻觉医嘱拦截 | ❌ | ✅ |
| HIPAA + PIPL 审计血缘（WORM · 6 年可重放） | ❌ | ✅ |

这层是医疗场景的生死线。**这就是护城河。**

---

## §D.1 合规脊柱（核心机制）

每一次模型调用，都在网关的 `/v1` 整组上被这条中间件拦截
（合规中间件 `medharness_compliance.go`，焊进 TokenAuth 之后）：

```
 client ─→ TokenAuth ─→ ① PHI 检测 ─→ ② 脱敏 ─→ ③ 数据分级签名（零信任）
                                                          │
        ⑥ 出站安全 ←── [ base relay 转发上游 ] ←── ⑤ 注入扫描 ←── ④ 模型白名单路由
              │
          审计双写（WORM + 哈希链）
```

不变量（任一不满足即拒）：

- **fail-closed**：任一闸门异常 → 通用 503，且 **deny 时 0 上游连接**（已证伪：DENY 路径不开一个上游 socket）。
- **零信任分级**：网关是分级签名的**唯一签发者**，model-router 是唯一验证者——客户端无法自报 `data_level` 蒙混。
- **base 无自主**：底座裸 `/api/route` 已杀；DMZ 只放行 `/v1/*`（网关）+ `/api/v1/*`（控制台）+ `/health`。
- **审计全量**：每次调用双写 `_audit_log`，不允许 fire-and-forget。

附加防线：出站不仅拦 PHI 回流，还按规则启发式**告警医疗幻觉**（虚假安全 / 武断确诊 / 擅自改量 / 伪造权威）。

---

## 任何客户端，一个端点

§D.1 挂在 `/v1` 整组，而这个组同时服务 OpenAI、Claude、Responses 三种协议——
所以**任何兼容客户端改个 `base_url` 就被纳管**：

| 客户端 | 指向端点 | 协议 |
|---|---|---|
| 业务后端 / Dify / RAG / Agent | `/v1/chat/completions` · `/v1/embeddings` | OpenAI |
| **Claude Code**（研发医疗系统 / 碰医疗数据） | `/v1/messages` | Anthropic Messages |
| **Codex CLI**（研发医疗系统 / 碰医疗数据） | `/v1/responses` | OpenAI Responses |
| Cursor / 其它工具 | `/v1/chat/completions` | OpenAI |

> **开发期 = 又一类流量来源**：研发用 Claude Code / Codex 写医疗系统时，把工具的 `base_url` 指向网关 + 用网关令牌，
> 开发期 prompt 跟生产流量走**同一条 §D.1 脊柱**——不再需要给每个 IDE 单独写 Hook。
>
> ⚠️ **配置 ≠ 强制**：要真正堵死绕过，需配合**网络出口管控**（开发机 / CI 只能经网关访问大模型）。
> 网关给的是统一闸门，强制性来自网络层。另一个隐性收益：开发者手里不再有真实 provider key，只有可吊销、带配额、全审计的网关令牌。

---

## 控制台（七屏）

合规官 + 运维的驾驶位。浏览器登录即用（自建 React 控制台，经 A0 控制面 BFF 读数，全程 0 患者 PHI）：

| 屏 | 看什么 |
|---|---|
| 总览 | 合规 / 安全态势、六道闸门状态 |
| 流量监控 | 实时流量桑基图 + 双色事件流 |
| 合规与报表 | 可检索合规事件 + 血缘图 + 哈希链 |
| 用量与成本 | 真实开销聚合（按模型 / 通道 / 趋势）+ 配额 |
| 接入 | 上游渠道 + 用户与分组管理 |
| 策略 | 配置 / 策略 + 变更审批 |
| 系统 | 系统与上游健康 |

> 角色分离：**系统管理员**管账号与渠道，**研发负责人**看态势与报表（脱敏视图）。患者 PHI 在任何屏恒为 0。

---

## 架构与部署

单机私有化、双网隔离、约 4-5GB / 4 cpu 一台 host 跑得动：

```
┌──────────────────────────────────────────────────────────────┐
│  Host（单机 · ≤30 人公司 · 约 4-5GB / 4 cpu）                  │
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
│  真实模型 key 只在网关渠道配置，绝不出 DMZ                     │
└──────────────────────────────────────────────────────────────┘
```

13 个容器镜像 = 11 个合规 MCP（phi-detector / desensitize / model-router / prompt-injection-scan /
outbound-safety / audit-log / internal-kb / vector-db / ci-trigger / pm-bridge / a0-api）+ 网关 + nginx。
multi-stage、非 root、Trivy 0 高危。

---

## 快速开始

### 路径 A · 全栈起栈 + 控制台（生产 staging）

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
> 「接入 → 用户与分组」（系统管理员）可建 / 改 / 停用账号。全程患者 PHI 恒为 0（员工身份仅在用户管理视图可见）。

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
| 🔒 **安全** | 入站 PHI 0 外泄（recall 1.0）· 出站 PHI 回流 / 幻觉拦截 · 注入防御 11/11 |
| 💰 **省钱** | 多渠道择优 + 缓存 + 实时成本可视 + 配额护栏 |
| 📋 **合规** | 数据分级零信任 · 异构审查 · WORM 审计血缘 6 年可重放 |
| 🟢 **稳定** | fail-closed · 多渠道冗余 · 594 测试 + 活栈 7 层 E2E |

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
| 成本**省钱智能**（较直连节省 / 缓存 ROI / 优化建议 / 日预算硬上限） | ❌ | ✅ |
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
| 报合规漏洞 / PHI 泄漏 | [GitHub Security Advisory](https://github.com/charliehzm/medharness/security/advisories/new)（私密 · **勿在 public issue 提**） |
| 早期客户接洽 / 深度合规咨询 | 微信 `supernera`（maintainer 直联 · 工作日 24h） |
| 贡献代码 | [CONTRIBUTING.md](CONTRIBUTING.md) → fork → PR |

**Star 这个仓库**如果你认同这个方向。Star 数会决定我们投入多少时间在社区版 vs 商业版上。

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

> 成为医疗机构上大模型的事实合规底座——让每一次医疗 AI 调用都可审计 / 可追溯 / 可重放。
