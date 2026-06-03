# MedHarness

> **医疗数据 SaaS 公司的 AI Coding 合规落地体系**
>
> 开源 · Apache 2.0 · HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南 四合规

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-CC_BY--SA_4.0-lightgrey.svg)](LICENSE-CC-BY-SA-4.0)
[![Status](https://img.shields.io/badge/Status-v1.0.0_stable-brightgreen.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-594_passed-brightgreen.svg)](#实测验证)
[![PHI Recall](https://img.shields.io/badge/PHI_recall-1.0_/_FP_0.09-brightgreen.svg)](#l5-合规层三道闸门)
[![Container](https://img.shields.io/badge/container-13_images-brightgreen.svg)](#容器化部署栈)

---

## 这个项目解决什么

你是医疗数据 SaaS 技术负责人。团队在用 Cursor / Claude Code 写代码。

**昨天**，一个工程师在 chat 框粘了 3 行病人样例数据让 LLM 帮 debug。这 3 行包含姓名 / 身份证号 / 病案号 / 入院日期。

**它们走了境外公共 API。**

恭喜，你刚违反了 **HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南** 四部法规。监管发现可以罚到全球营业额 4%。

**MedHarness 让这种事不可能发生**：

- Hook 自动扫所有 prompt（**PHI 召回 100% / 误报 9%**，220 个合成样本测）
- 想带数据进 prompt？必须先经 `phi-desensitize`（AES-256-GCM + AAD 上下文绑定，**p99 加密 0.02ms**）
- LLM 调用必须经 `mcp-model-router`（5 层 runtime gate，**11/11 越狱攻击全防**）
- 每个 tool / model / Skill 调用全量落 `mcp-audit-log`（3 层 WORM + 哈希链 + 6 年保留）
- 合规审查必须用**异构模型**（防 v2.0 "自证清白"教训，runtime 不可绕过）

**这不是文档承诺。这是 60+ 个 leaf 的代码 + 594 个测试（含活栈 E2E 七层）+ 4 个红队演练 + 9 个 ADR · CI weekly enforce**。

---

## 一眼数字

| 维度 | 数字 |
|---|---|
| 测试 | 594 passed（活栈 7 层 E2E + 跨浏览器 UI）|
| 红队演练 | 4 全实装（PHI / router / audit / injection） |
| CI gates | 5 enforced（每周一自动跑 + 失败自动开 issue） |
| PR merged | 80+ leaf-level |
| ADR | 9 落档（每个决策含替代 + 否决理由） |
| 容器 | 13 image（11 MCP + 网关 + Console）· 全 Trivy scan · 0 high vuln |
| 漏出 | 0 PHI · 0 contract violations |

---

## 你现在能拿到什么

### 已落地（v1.0.0 社区版 · 合规网关 + Console 全栈）

| 能力 | 实现 | 落地证据 |
|---|---|---|
| **§D.1 合规脊柱** | `vendor/new-api/middleware/medharness_compliance.go` | 每次模型调用必经 phi→脱敏→签级→路由→注入→出站；fail-closed · 通用 503 · deny 时 0 上游连接 |
| **PHI 检测** | `mcp/phi-detector/` | Presidio + 11 中文识别器 + 6 上下文规则 · recall 1.0 / FP 0.09 |
| **PHI 脱敏 + KMS** | `mcp/desensitize/` | AES-256-GCM + AAD 5 字段 · FileKeyProvider 多代轮换 · 云 KMS 接口预留 |
| **LLM 路由 runtime gate** | `mcp/model-router/` | 5 层 PolicyCore + 异构性强制 · 客户端不可自报分级（B1 零信任）|
| **出站输出安全** | `mcp/outbound-safety/` | 有害拦截 + PHI 回流 + 医疗幻觉启发式（告警）· 流式分块重组抗绕过 |
| **WORM 审计日志** | `mcp/audit-log/` | hashchain + fallback + 3 态 state machine + ClickHouse |
| **Prompt injection 防御** | `mcp/prompt-injection-scan/` | 5 类攻击 detector · 25 case corpus · block rate 1.0 |
| **A0 Console BFF** | `mcp/a0-api/` | 只读聚合 + 用户管理写代理 + 会话 token · 全程 0 患者 PHI 守卫 |
| **React Console** | `web/` | 总览/流量/合规/用量成本/接入/策略/系统 · 持久登录 · 实时成本 · 用户管理 |
| **配额 / 实时成本** | `mcp/a0-api/` | 底座配额强制（预扣+结算）· `/cost` 聚合 new-api 真实用量 |
| **11 MCP + 网关 + Console 容器化** | `deploy/docker-compose.prod.yml` | 13 image · multi-stage 非 root + Trivy · DMZ/internal 双网 + 逐服务资源限 |
| **TLS 反代 + egress allowlist** | `deploy/nginx/` | self-signed + BYO · TLS 1.2/1.3 · 仅放行 `/v1/*` + `/api/v1/*`，杀裸 `/api/route` |
| **红队 CI cron** | `.github/workflows/compliance.yml` | weekly Monday · 失败自动开 issue · 90-day artifact |

### 1.0 之后 / 商业版边界

社区版给的是**真实可跑的合规网关 + 用量可视**；以下是商业版差异化（社区版以「即将推出」诚实标注，绝不冒充已建）：

- **训练好的中文医疗 PHI 模型**（社区版为规则 + Presidio）· **出站幻觉的训练版分类器**（社区版为规则启发式）
- **成本省钱智能**（较直连节省 / 缓存 ROI / 优化建议 / 日预算硬上限）· 社区版只给真实用量与开销
- **托管 MCP 集群**（KMS / WORM）· **分布式向量检索 + 训练 reranker**（社区版为单机 stdlib）
- **OIDC / 多租户 / 计费 / 24x7 合规 SLA**

详见 [docs/community-vs-commercial.md](docs/community-vs-commercial.md)。

---

## L5 合规层 · 三道闸门

医疗 SaaS 公司的合规生死线。MedHarness 落地这三道闸门：

```
┌─────────────────────────────────────────────────────────────┐
│  闸门一  PHI 出站扫描 (UserPromptSubmit Hook)                  │
│         开发者粘 PHI 到 chat → Hook 自动扫描 → 阻断          │
│         recall 1.0 · FP 0.09 · 220 正 + 110 负样本验证       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  闸门二  脱敏 + KMS (mcp-desensitize)                         │
│         业务真要带数据 → 主动调 desensitize API              │
│         AES-256-GCM + AAD 绑定 5 字段 · 反查表 ClickHouse    │
│         p99 加密延迟 0.02ms                                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  闸门三  模型路由 runtime gate (mcp-model-router)             │
│         LLM 调用必经此 · 5 层 PolicyCore                      │
│         allowlist + role + data_level + heterogeneity        │
│         < 5ms overhead · 11/11 router bypass 全防            │
└─────────────────────────────────────────────────────────────┘
                          ↓
              所有动作落审计 (mcp-audit-log)
              WORM · 哈希链 · 6 年保留 · 4 小时可重放
```

三道闸门**不冗余**：闸门一管"无意识泄露"，闸门二管"主动带数据"，闸门三管"运行时不可绕"。Swiss cheese model — 任意一层漏，下一层挡。

附加防线（第四层）：`mcp-prompt-injection-scan` · 5 类攻击家族 · 25 case 合成 corpus · drill 4 block rate 1.0 / FP 0.0。

详见 [`design.md` ADR-01/02/03/04/07](openspec/changes/feat-edge-tier-production-v0.5.0/design.md)。

---

## 6 层架构

```
L6 治理层   技术委员会(双周) │ 合规委员会(月度) │ Skill Owner 制
─────────────────────────────────────────────────────────────────
L5 合规层   数据分级 │ PHI 脱敏 │ 模型可用性矩阵 │ 注入防护 │ 审计血缘
           ↑↓ 横切，所有动作必经
─────────────────────────────────────────────────────────────────
L4 SOP 层   12 步主通道 + 5 步 micro 通道（速度 / 合规双轨）
─────────────────────────────────────────────────────────────────
L3 Skill 层 23 Skill：合规 5 / 通用 16 / 别名 2
─────────────────────────────────────────────────────────────────
L2 Harness  Orchestrator + 6 Sub-agent │ Tiered Memory │ 9 Hook │ 11 MCP
─────────────────────────────────────────────────────────────────
L1 模型层   编码 / Review / 架构 / 医学长文 / 脱敏小模型
           异构性 runtime 强制（防 v2.0 "自证清白"教训）
```

---

## 容器化部署栈

v1.0.0 已 production-ready：

```
┌─────────────────────────────────────────────────────────────┐
│  Host (single instance · 30-人公司部署 · 约 4-5GB / 4 cpu)   │
│                                                              │
│  ┌─────────────┐                                             │
│  │   nginx     │  ← DMZ · 仅放行 /v1/* + /api/v1/* + /health │
│  │  (TLS 443)  │     TLS 1.2/1.3 + HSTS · 杀裸 /api/route   │
│  └──────┬──────┘                                             │
│         │                                                    │
│  ┌──────┴───────────────────────────────────────────────┐   │
│  │  medharness_internal (internal: true · 不暴露 host)   │   │
│  │                                                       │   │
│  │  new-api 网关 (§D.1 脊柱)   a0-api (Console BFF)      │   │
│  │  phi-detector  desensitize  model-router  injection  │   │
│  │  outbound-safety  audit-log                          │   │
│  │  ci-trigger    internal-kb  pm-bridge     vector-db  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  Host volumes:                                               │
│   /data/medharness/audit       (WORM + chattr +a)           │
│   /data/medharness/keystore    (chmod 0o400)                │
│   /etc/medharness/tls          (TLS cert · self-signed/BYO) │
└─────────────────────────────────────────────────────────────┘
```

---

## 三种开始方式

### 路径 A · 5 分钟试一下（开发机）

```bash
git clone https://github.com/charliehzm/medharness.git && cd medharness
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 跑全量测试 + 4 红队演练
.venv/bin/python -m pytest tests/                       # 594 passed（活栈层需先起栈）
bash tests/red-team-drills/run_all.sh                    # 4 drills + 5 gates

# 跑 12 步 SOP（合成 PHI 走完合规闸门）
bash dryrun_e2e_v2.sh --ci                               # Step 0-12 pass
```

### 路径 B · 合规网关 + Console 全栈（生产 staging）

```bash
# 1. 生成 TLS cert（默认 self-signed · BYO 见 ADR-06）
bash scripts/gen-tls.sh

# 2. 配置 env（复制模板后填密钥）
cp deploy/.env.production.example deploy/.env.production
#   必填：MODEL_ROUTER_TIER_SECRET（网关↔model-router 同值，签级密钥）
#         A0_SESSION_SECRET（≥32B，Console 会话 token 签名）
#   选填：NEW_API_ADMIN_TOKEN / NEW_API_ADMIN_USER_ID（启用 Console 用户管理写口；
#         为 new-api root 的 access_token + id，仅注入 a0-api 容器内网，绝不出 DMZ）

# 3. 一键构建并启动全栈（13 image：11 MCP + new-api 网关 + nginx/Console）
docker compose -f deploy/docker-compose.prod.yml \
               --env-file deploy/.env.production up -d --build

# 4. 健康检查
docker compose -f deploy/docker-compose.prod.yml ps      # 全 healthy
curl -k https://localhost/health                          # DMZ 健康

# 5. 登录 Console（默认 new-api root：admin / 首启动控制台所设密码）
#    浏览器开 https://localhost/ → 登录 → 总览/流量/合规/用量成本/接入/策略/系统
```

> **首次部署校验**：登录后「总览」六道闸门应显示「已上线」，「用量与成本」显示真实
> 聚合开销（无流量则 $0.00），「接入 → 用户与分组」（系统管理员）可建/改/停用账号。
> 全程患者 PHI 恒为 0（员工身份仅在用户管理视图可见）。

### 路径 C · 离线包部署（T13 完成后可用）

待 Phase 4 完成。届时单 tarball + `install.sh` 一键部署到客户内网。

---

## FAQ

**Q: 这跟 LangChain / LlamaIndex 是什么关系？**
不替代。LangChain / LlamaIndex 是 LLM 应用框架（让你写 RAG）· MedHarness 是合规工程体系（确保你写的 RAG 不违法）。两者正交，可共存。

**Q: 这跟 spec-kit / OpenSpec 什么关系？**
OpenSpec 是我们用的 spec 工具（已加 12+5 双通道扩展）· spec-kit 是 GitHub 的通用 spec 工具。MedHarness 在 OpenSpec 之上做了医疗合规专属的 Step 0 (合规预检) + Step 10 (合规 Gate) + Step 12 (审计冻结)。

**Q: 这跟 Cursor / Claude Code 什么关系？**
Cursor / Claude Code 是 AI 编辑器（IDE）· MedHarness 是给 Claude Code 用的合规体系。我们选 Claude Code 作为企业标准 IDE（Skill 系统 + Hook 治理友好）· Cursor 仅限白名单场景（前端原型 / 公开文档）。

**Q: 我们才 10 个工程师，这套体系是不是太重？**
v1.0.0 部署堆约 4-5GB mem / 4 cpu · 一台 host 跑得动。SOP 有 5 步 micro 通道处理轻量改动（< 2 文件 / 仅文档 / 配置）· 不是所有 PR 都要走 12 步。

**Q: 我已经有 LGTM / Prometheus / Loki 监控，需要 mcp-audit-log 吗？**
需要。监控记的是 system metrics · audit-log 记的是 AI 决策血缘（哪个 prompt / 哪个模型 / 哪个 Skill / 哪条数据）。HIPAA 6 年可重放是监管硬要求，不是可选项。

**Q: 训练好的中文医疗 PHI detector 在哪？**
社区版用规则 + Presidio + 11 中文识别器（recall 1.0 是合成语料）· 真实生产场景需要训练过的模型。这是商业版的差异化点（见社区版 vs 商业版表）。

**Q: 不适合谁？**
通用 SaaS（用 spec-kit）· 医疗器械 SaMD（用 IEC 62304 工具链）· 个人爱好者（项目过重）· 不接触 PHI 的纯前端项目（不需要 L5 合规层）。

---

## 与开源生态的关系

| 我们用 | 我们加 |
|---|---|
| [microsoft/presidio](https://microsoft.github.io/presidio/) | 中文医疗 recognizer + 31 fields.yml + RegexOnlyNlpEngine workaround |
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 12+5 双通道 SOP · Step 0/10/12 合规扩展 |
| [github/spec-kit](https://github.com/github/spec-kit) | verify / compliance gate / audit freeze |
| [anthropics/skills](https://github.com/anthropics/skills) | 医疗专属 21+2 Skill |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 8 件医疗合规专属 MCP |

**我们独有**（核心 IP，不在上述任何生态里）：

- **异构性 runtime gate**（model-router 5 层 PolicyCore · 不可绕）
- **3 层 WORM 审计**（ClickHouse + chattr +a + fallback state machine + 哈希链）
- **12+5 双通道 SOP**（速度 / 合规双轨 · 不是非此即彼）
- **PIPL + 健康医疗数据安全指南本土化合规层**
- **90 天督导 + 主理人接棒培训方法论**

---

## 12 步 SOP

```
Step 0   合规预检         数据分级 + 模型 allowlist
Step 1-3 PRD / TDD / OpenSpec    业务诉求 → spec
Step 4-5 任务拆解 + Mock 数据    合成测试数据
Step 6   实现             PHI 任务强制 phi-desensitize 前置
Step 7   Verify           一次通过率 ≥ 75%
Step 8   Review + Debug   Reviewer-Agent 异构模型
Step 9   Mocking 测试     联调
Step 10  合规 Gate        Compliance-Agent 异构 + 阻断
Step 11  合规整改         仅 Step 10 有整改时
Step 12  审计冻结归档     AUDIT_BUNDLE 哈希链上链
```

**5 步 micro 通道**（≤ 2 文件 / 文档 / 配置）：见 [研发交付SOP-v2.2-micro.md](研发交付SOP-v2.2-micro.md)。

---

## 5 条红线（任何 PR 必读）

1. **PHI 永不裸入 prompt** — 含原始患者标识必须先经 `phi-desensitize`
2. **模型按 allowlist 路由** — 不允许直连境外公共 API
3. **审计全量记录** — 每次 tool / 模型 / Skill 调用必落 `mcp-audit-log`
4. **测试数据合规** — 禁止生产采样脱敏，强制走 `test-data-generation` 合成
5. **绕过 Hook = 合规违规** — 关 Hook 需双委员会签字

---

## 实测验证

**当前 main**：

```bash
.venv/bin/ruff check .                        # clean
.venv/bin/python -m pytest tests/              # 594 passed
bash tests/red-team-drills/run_all.sh          # 4 drills + 5 gates 全过
bash dryrun_e2e_v2.sh --ci                     # Step 0-12 pass
bash scripts/e2e_full.sh                       # 活栈 7 层（离线/网关/数据/闭环/失败闭合/冒烟/UI）全绿
```

**Red-team CI**（`.github/workflows/compliance.yml` · 每周一 09:00 CST）：

| Drill | Threshold | 实测 |
|---|---|---|
| drill 1 PHI recall | ≥ 92% | 1.0 |
| drill 1 FP rate | ≤ 15% | 0.09 |
| drill 2 router bypass | 11/11 deny | 11/11 |
| drill 3 audit chain | intact + tampered detected | 全过 |
| drill 4 injection block_rate | ≥ 95% | 1.0 |
| drill 4 injection fp_rate | ≤ 10% | 0.0 |

**Docker build CI**（`.github/workflows/docker-build.yml` · 每周一 10:00 CST · Trivy scan）：

| 维度 | 阈值 | 实测 |
|---|---|---|
| 生产 MCP image | < 500MB | 4/4 通过 |
| stub MCP image | < 200MB | 4/4 通过 |
| Trivy HIGH+CRITICAL | 0 | 0 |

失败时自动开 GitHub Issue（label: `compliance` + `red-team-regression` + `sev-2`）。

---

## 社区版 vs 商业版

| 能力 | 社区版（Apache 2.0） | 商业版 |
|---|---|---|
| 6 层架构骨架 + 23 Skill + 11 MCP + 合规网关 + Console（容器化） | ✅ | ✅ |
| 4 红队 drill + 5 CI gates | ✅ | ✅ + Slack/PagerDuty |
| 31 fields.yml | ✅ 通用 | ✅ + 客户化字段 |
| 训练好的中文医疗 phi-detector 模型 | ❌ | ✅ |
| 托管 MCP 集群（KMS / WORM） | ❌ | ✅ |
| Dashboard SaaS | ❌ | ✅ |
| 24x7 合规事件 SLA | ❌ | ✅ |
| 1 对 1 督导 / 现场培训 | ❌ | ✅ |

**License 永久承诺**：已发布的社区版组件，license **永久** Apache 2.0 / CC BY-SA 4.0。
不会效仿 MongoDB / Elastic 改 SSPL / BSL。

详见 [docs/community-vs-commercial.md](docs/community-vs-commercial.md)。

---

## 加入

| 我想... | 路径 |
|---|---|
| 提问 / 案例分享 | [GitHub Discussions](https://github.com/charliehzm/medharness/discussions)（推荐 · 可被搜索） |
| 报 bug / 提 feature | [GitHub Issues](https://github.com/charliehzm/medharness/issues/new/choose) |
| 报合规漏洞 / PHI 泄漏 | [GitHub Security Advisory](https://github.com/charliehzm/medharness/security/advisories/new)（私密 · **勿在 public issue 提**） |
| 早期客户接洽 / 深度合规咨询 | 微信 `supernera`（maintainer 直联 · 工作日 24h） |
| 贡献代码 | [CONTRIBUTING.md](CONTRIBUTING.md) → fork → PR |

**Star 这个仓库**如果你认同这个方向。Star 数会决定我们投入多少时间在社区版 vs 商业版上。

---

## License + 引用

- 代码：[Apache 2.0](LICENSE)
- 文档：[CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0)
- 安全披露：[SECURITY.md](SECURITY.md)
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

```bibtex
@software{medharness2026,
  title  = {MedHarness: Compliance Engineering for Medical AI Coding},
  author = {MedHarness Maintainers},
  year   = {2026},
  url    = {https://github.com/charliehzm/medharness},
  license = {Apache-2.0}
}
```

---

## 项目目标

> 成为医疗数据 SaaS 公司用 AI Coding 的事实合规标准。
>
> 让每一行 AI 写的医疗代码都可审计 / 可追溯 / 可重放。
