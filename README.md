# MedHarness

> **Harness Engineering for Medical AI Coding**
>
> 一套面向医疗数据 SaaS / 数据中台公司的开源 AI Coding 落地体系。
> HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南 全部合规。
> 从"零散个人用 AI 编辑器"到"企业级、可审计、可演进、可容器化部署"。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-CC_BY--SA_4.0-lightgrey.svg)](LICENSE-CC-BY-SA-4.0)
[![Status](https://img.shields.io/badge/Status-v0.5.0--edge_(in_progress)-blue.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/Tests-337_passed-brightgreen.svg)](#实测验证)
[![PHI Recall](https://img.shields.io/badge/PHI_Recall-1.0_/_FP_0.09-brightgreen.svg)](#l5-合规层落地证据)

---

## 适合谁

| 你是 | MedHarness 给你 |
|---|---|
| 10-50 人医疗数据 SaaS 技术负责人 | 完整 SOP + 合规闸门 + 容器化部署栈 |
| 互联网医院技术团队 | 速度 / 合规双满足的 12+5 步双通道 |
| 医院信息部 AI 化项目 | 完整培训方法论 + 90 天督导 |
| 药企 CRO 数字化部 | AUDIT_BUNDLE 哈希链 + 6 年 WORM |

**不适合谁**：通用 SaaS（用 spec-kit）、医疗器械 SaMD（用 IEC 62304 工具链）、个人爱好者（项目过重）。

---

## v0.5.0-edge 当前进度（2026-05-25）

**Phase 1-3 大部分完成 · Phase 4 待启动**

| Task Group | Status | 核心交付物 |
|---|---|---|
| **T1** phi-detector | ✅ | Presidio + 11 中文 recognizer + 31 fields.yml + RegexOnlyNlpEngine workaround |
| **T2** desensitize-kms | ✅ | AES-256-GCM + AAD 绑定 + FileKeyProvider + 云 KMS 接口预留 |
| **T3** model-router | ✅ | 5 层 PolicyCore + 异构性 runtime gate + 11 bypass 全防 |
| **T4** audit-log WORM | ✅ | hashchain + fallback writer + 3 态 state machine + ClickHouse schema |
| T5 drill 2 router bypass | ✅ absorbed by T3.8 | 11 攻击 case · 全部 deny |
| T6 drill 3 audit replay | 🔄 partial by T4.9 | hash chain 验证完整 · 语义重放推迟 v0.6+ |
| **T7** prompt-injection | ✅ | 5 类 detector + 25 case corpus + 95% block rate gate |
| **T8** CI 红队 cron | ✅ | GitHub Actions weekly + auto-issue + 90-day artifact |
| **T9** 8 MCP Dockerfile | ✅ | multi-stage + 非 root + Trivy scan + per-MCP requirements |
| **T10** docker-compose | ✅ | 8 services + 双网（DMZ + internal）+ resource limits |
| **T11** TLS | ✅ | self-signed + BYO 双路径 + TLS 1.2/1.3 + HSTS |
| T12 backup/restore/upgrade/teardown | 🟡 in progress | T12.1 backup+restore ✅ · T12.2/T12.3 待完成 |
| T13-T15 离线包 | ⏳ next | offline tarball + install.sh + verify.sh |
| T16-T20 培训 + 合规文档 | ⏳ | training materials + compliance runbooks |

**累计**：
- **60+ leaves merged** · **80+ PR**
- **337 tests + 1 skipped** · **ruff clean**
- **4 red-team drills + 5 gates** CI enforced（drill 1 PHI / drill 2 router / drill 3 audit / drill 4 injection / recall_gate）
- **9 ADRs** 落档（design.md）
- **8 MCP Dockerfile** 全部 < 500MB（生产）/ < 200MB（stub）· Trivy scan integrated
- **0 漏出 · 0 contract violations**

详见 [openspec/changes/feat-edge-tier-production-v0.5.0/](openspec/changes/feat-edge-tier-production-v0.5.0/)。

---

## L5 合规层落地证据

三道闸门 · 全部实施 + 测试 + CI enforce：

| 闸门 | 实现 | 落地指标 |
|---|---|---|
| **闸门一** PHI 出站扫描 | `mcp/phi-detector/` · Presidio + 11 中文识别器 + 6 上下文规则 | recall **1.0** / FP **0.09** · 220 正样本 + 110 负样本 |
| **闸门二** 脱敏 + KMS | `mcp/desensitize/` · AES-256-GCM + AAD 绑定 5 字段 + FileKeyProvider 多代轮换 | p99 加密延迟 **0.02ms** · cloud KMS 接口预留 |
| **闸门三** 模型路由 runtime gate | `mcp/model-router/` · 5 层 PolicyCore + heterogeneity + circuit breaker + rate limit | < **5ms** overhead · 11/11 router bypass 全防 |

第四层 prompt-injection 防御：`mcp/prompt-injection-scan/` · 5 类攻击家族 · drill 4 block rate **1.0** / FP rate **0.0**。

详见 [design.md ADR-01/02/03/04/07](openspec/changes/feat-edge-tier-production-v0.5.0/design.md)。

---

## 容器化部署栈

v0.5.0-edge 已实现 production-ready 容器化部署：

```
┌─────────────────────────────────────────────────────────────┐
│  Host (single instance · 30-人公司部署)                       │
│                                                              │
│  ┌─────────────┐                                             │
│  │   nginx     │  ← DMZ entrypoint                           │
│  │  (TLS 443)  │     TLS 1.2/1.3 + HSTS + Mozilla cipher    │
│  └──────┬──────┘                                             │
│         │                                                    │
│  ┌──────┴───────────────────────────────────────────────┐   │
│  │  medharness_internal (internal: true · 不暴露 host)   │   │
│  │                                                       │   │
│  │  phi-detector  desensitize  model-router  audit-log  │   │
│  │  ci-trigger    internal-kb  pm-bridge     vector-db  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  Host volumes:                                               │
│   - /data/medharness/audit       (WORM + chattr +a)         │
│   - /data/medharness/keystore    (chmod 0o400)              │
│   - /etc/medharness/tls          (TLS cert)                 │
└─────────────────────────────────────────────────────────────┘
```

**启动命令**（T13 install.sh 完成后会封装）：

```bash
# 1. 生成 TLS cert（默认 self-signed · BYO cert 见 ADR-06）
bash scripts/gen-tls.sh

# 2. 构建 8 MCP images
bash scripts/docker-build.sh phi-detector
# ... 或 buildkit matrix 见 .github/workflows/docker-build.yml

# 3. 启动 production stack
cp deploy/.env.production.example deploy/.env.production
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production up -d

# 4. 健康检查
docker compose ps  # 所有 service 应 healthy
curl -k https://localhost/api/route  # 走 nginx → model-router
```

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
L2 Harness  Orchestrator + 6 Sub-agent │ Tiered Memory │ 9 Hook │ 8 MCP
─────────────────────────────────────────────────────────────────
L1 模型层   编码 / Review / 架构 / 医学长文 / 脱敏小模型 + 合规独立模型
           异构性 runtime 强制（防 v2.0 "自证清白"教训）
```

详见 [docs/architecture/](docs/architecture/)。

---

## 5 分钟上手

```bash
# 1. clone
git clone https://github.com/charliehzm/medharness.git
cd medharness

# 2. install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 3. 跑全量测试 + 红队演练
.venv/bin/python -m pytest tests/                      # 337 tests · ruff clean
bash tests/red-team-drills/run_all.sh                   # 4 drills + 5 gates 全 enforce

# 4. dry-run 12 步 SOP（合成 PHI · 走完合规闸门）
bash dryrun_e2e_v2.sh --ci

# 输出：
# ✅ Step 0-12 全部通过
# ✅ AUDIT_BUNDLE.tar.gz 已生成（含哈希链）
# ✅ 4 red-team drills 全 enforce（PHI / router / audit / injection）
```

容器化部署见上面 [容器化部署栈](#容器化部署栈)。

---

## 与开源生态的关系

| 我们用什么 | 我们加什么 |
|---|---|
| [microsoft/presidio](https://microsoft.github.io/presidio/) | 中文医疗 recognizer + 31 fields.yml + 上下文规则 + RegexOnlyNlpEngine workaround |
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 12 步 + 5 步双通道 SOP |
| [github/spec-kit](https://github.com/github/spec-kit) | verify / compliance gate / audit freeze 扩展 |
| [anthropics/skills](https://github.com/anthropics/skills) | 医疗专属 21+2 Skill |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 8 件医疗合规专属 MCP |

**我们独有**（核心 IP）：
- 异构性强制 runtime gate（model-router 5 层 PolicyCore · 不可绕）
- AUDIT_BUNDLE 哈希链 + 3 层 WORM（ClickHouse + chattr +a + fallback state machine）
- 12+5 双通道 SOP
- 90 天督导 + 主理人接棒培训方法论
- PIPL + 健康医疗数据安全指南本土化合规层
- 8 个医疗专属 MCP server（Docker 化 + 非 root + Trivy scan）

详见 [docs/architecture/dependency-graph.md](docs/architecture/dependency-graph.md)。

---

## 12 步 SOP

```
Step 0   合规预检         ← 数据分级 + 模型 allowlist
Step 1-3 PRD / TDD / OpenSpec ← 业务诉求 → spec
Step 4-5 Task / Mock 数据  ← 拆解 + 合成测试数据
Step 6   实现             ← PHI 任务强制 phi-desensitize 前置
Step 7   Verify           ← 一次通过率必 ≥ 75%
Step 8   Review + Debug   ← Reviewer-Agent 异构模型
Step 9   Mocking 测试     ← 联调
Step 10  合规 Gate        ← Compliance-Agent 异构 + 阻断
Step 11  合规整改         ← 仅 Step 10 有整改时
Step 12  审计冻结归档     ← AUDIT_BUNDLE 哈希链上链
```

**5 步 micro 通道**（< 2 文件 / 仅文档 / 测试加固 / 配置）：见 [研发交付SOP-v2.2-micro.md](研发交付SOP-v2.2-micro.md)。

---

## 红线（任何 PR 必读）

1. **L4 PHI 永不裸入 prompt** — 含原始患者标识必须先经 `phi-desensitize`
2. **模型按 allowlist 路由** — 不允许直连境外公共 API
3. **审计全量记录** — 每次 tool / 模型 / Skill 调用必落 `mcp-audit-log`
4. **测试数据合规** — 禁止生产采样脱敏，强制走 `test-data-generation` 合成
5. **绕过 Hook = 合规违规** — 关 Hook 需双委员会签字

---

## 实测验证

**当前 main commit**：通过完整 CI gate

```
.venv/bin/ruff check .                          # clean
.venv/bin/python -m pytest tests/                # 337 passed, 1 skipped
bash tests/red-team-drills/run_all.sh            # all drills + gates pass
bash dryrun_e2e_v2.sh --ci                       # Step 0-12 pass
```

**Red-team drills CI enforcement**（`.github/workflows/compliance.yml` · weekly Monday 09:00 CST）：

```
drill 1 PHI recall ≥ 92%                          实测 recall=1.0  FP=0.09
drill 2 router bypass 11/11 deny                  实测 11/11 deny
drill 3 audit chain integrity + tamper detection  实测 chain_intact + tampered_detected
drill 4 prompt injection block_rate ≥ 95%         实测 block_rate=1.0  fp_rate=0.0
recall_gate FP ≤ 15%                              实测 0.09
```

**Docker build CI**（`.github/workflows/docker-build.yml` · weekly Monday 10:00 CST · Trivy scan）：

```
8 MCP images:
  phi-detector / desensitize / model-router / audit-log     生产 < 500MB
  ci-trigger / internal-kb / pm-bridge / vector-db          stub  < 200MB
Trivy --severity HIGH,CRITICAL                             0 high vuln
```

---

## 社区版 vs 商业版

| 能力 | 社区版（Apache 2.0） | 商业版（Proprietary） |
|---|---|---|
| 6 层架构骨架 | ✅ | ✅ |
| 23 Skill + 6 Sub-agent | ✅ | ✅ |
| 8 MCP server（容器化） | ✅ | ✅ |
| 4 个红队 drill + 5 gates | ✅ | ✅ + Slack/PagerDuty 集成 |
| 31 fields.yml | ✅ 通用 | ✅ + 客户化字段 |
| 训练好的中文医疗 phi-detector | ❌ | ✅ |
| 托管 MCP 集群（KMS / WORM） | ❌ | ✅ |
| Dashboard SaaS | ❌ | ✅ |
| 24x7 合规事件 SLA | ❌ | ✅ |
| 1 对 1 督导 / 现场培训 | ❌ | ✅ |

详见 [docs/community-vs-commercial.md](docs/community-vs-commercial.md)。

---

## 路线图

### v0.5.0-edge（当前）
- Phase 1 ✅ 4 个核心 MCP（T1-T4）：phi-detector / desensitize / model-router / audit-log
- Phase 2 ✅ 红队 + CI（T5-T8）：4 drills + 5 gates · GitHub Actions weekly cron
- Phase 3 🟡 部署编排（T9-T12）：Docker + compose + TLS ✅ · backup/restore ✅ · upgrade/teardown 进行中
- Phase 4 ⏳ 离线包 + 培训文档（T13-T20）：offline tarball · install.sh · 合规 runbook · 培训材料

### v0.6+（规划）
- 真 ClickHouse integration（v0.5.0 mock-only）
- drill 3 语义重放（v0.5.0 仅 hash chain）
- 真实 jailbreak corpus 校准（v0.5.0 100% synthetic）
- 云 KMS（Vault / 阿里云 / AWS）proxy-mode integration
- 增量 backup + 多 host 部署

---

## 社区 / 联系

| 渠道 | 用途 | SLA |
|---|---|---|
| [GitHub Discussions](https://github.com/charliehzm/medharness/discussions) | 提问 / 想法 / 案例分享 | 24h 内首次回复 |
| [GitHub Issues](https://github.com/charliehzm/medharness/issues/new/choose) | bug / feature / case study | 同上 |
| [GitHub Security Advisory](https://github.com/charliehzm/medharness/security/advisories/new) | **PHI 泄漏 / 合规漏洞**私密披露（**勿在 public issue 提**） | 2h（高敏） |
| 微信：`supernera`（maintainer 直联） | 个人沟通 / 早期客户接洽 / 行为准则上报 | 工作日 24h |

> 推荐**先开 [Discussion](https://github.com/charliehzm/medharness/discussions)**：可被搜索 + 后来者受益。私聊适合早期客户 / 合规深聊。

---

## 贡献 / 安全 / License

- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 安全漏洞披露：[SECURITY.md](SECURITY.md)（**勿在 public issue 提交合规 / 安全漏洞**）
- 代码 License：[Apache 2.0](LICENSE)
- 文档 License：[CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0)

**License 永久承诺**：已发布的社区版组件，license 永久 Apache 2.0 / CC BY-SA 4.0。
不会效仿 MongoDB / Elastic 改 SSPL / BSL。

---

## 引用 / Cite

```bibtex
@software{medharness2026,
  title  = {MedHarness: Harness Engineering for Medical AI Coding},
  author = {MedHarness Maintainers},
  year   = {2026},
  url    = {https://github.com/charliehzm/medharness},
  license = {Apache-2.0}
}
```

---

## 一句话愿景

> **5 年后，所有想用 AI Coding 的医疗数据 SaaS 公司，第一周必须先 fork MedHarness。**
