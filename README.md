# MedHarness

> **Harness Engineering for Medical AI Coding**
>
> 一套面向中国医疗数据 SaaS / 互联网医院 / 医院信息化 / 药企-CRO 团队的开源 AI Coding 控制平面。
> 它把 PHI 脱敏、模型 allowlist 路由、全量审计、红队演练和生产编排串成一条可落地的工程链路。
> 当前处于 v0.5.0-edge / Phase 3，安全与部署主线已经进入生产化阶段，但仍不是合规认证产品。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-CC_BY--SA_4.0-lightgrey.svg)](LICENSE-CC-BY-SA-4.0)
[![Status](https://img.shields.io/badge/Status-v0.5.0--edge-orange.svg)](CHANGELOG.md)

---

## 适合谁

| 你是 | MedHarness 给你 |
|---|---|
| 10-50 人医疗数据 SaaS 技术负责人 | 6 个月落地的完整 SOP + 合规闸门 |
| 互联网医院技术团队 | 速度 / 合规双满足的 12+5 步双通道 |
| 医院信息部 AI 化项目 | 完整培训方法论 + 90 天督导 |
| 药企 CRO 数字化部 | AUDIT_BUNDLE 哈希链 + 6 年审计留痕 / WORM 设计 |

**不适合谁**：通用 SaaS（用 spec-kit）、医疗器械 SaMD（用 IEC 62304 工具链）、个人爱好者（项目过重）。

## 当前状态

- 版本定位：`v0.5.0-edge`，Phase 3 edge-tier productionization。
- 已合并主线：T1-T10 已闭合，包含 prompt-injection gate、red-team cron、8 MCP Dockerfile、生产 Compose 拓扑。
- 正在推进：T11 TLS 双路径、443、证书生成 / 过期检查（未合并主线）。
- 后续方向：备份恢复、离线打包、镜像注册表、SBOM / multi-arch buildx。
- 准确性边界：当前 README 描述的是工程控制面和部署骨架，不宣称已经取得任何监管认证。

## 中国语境

- 合规工程基线以中国法规和指南为主：`个人信息保护法（PIPL）`、`数据安全法`、`网络安全法`、`健康医疗数据安全指南（试行）`。
- `HIPAA` 仅作为海外医疗合规工程参考，不作为本项目唯一基线，也不替代中国法务 / 合规审查。
- README 中的 `PHI` 是工程简称，在中国场景下对应个人健康医疗信息、敏感个人信息和可识别患者数据。
- 文档、工作流、字段命名、红队材料和运维交接默认中文优先，便于国内研发、信息科、合规和交付团队共同使用。
- 目标部署场景以中国境内私有化 / 内网 / 医疗数据隔离环境为主；默认不要求直连境外公共 LLM API。
- 所有“合规”表述均指工程控制与审计证据建设，不等同于法律意见、等保测评结论或医疗器械注册结论。

## 核心能力

MedHarness 的核心不是“调用一个模型”，而是把医疗场景里的 AI 使用变成一条受控链路：

```
业务请求
  → PHI 检测 / 脱敏
  → 模型 allowlist 路由
  → MCP 工具执行
  → 全量审计 / 哈希链 / WORM
  → 红队演练 + CI gate + 生产部署
```

关键控制点：

- **PHI 不裸入 prompt**：`phi-detector` + `desensitize` 前置。
- **模型不直连失控**：`model-router` 按 vendor family / data level / role allowlist 路由。
- **审计不断链**：`audit-log` 记录工具、模型、Skill 调用证据，v0.5.0-edge 以 hashchain / fallback 基础能力为主。
- **安全不靠口号**：prompt-injection drill、recall gate、Docker build + scan gate 进 CI。
- **部署不是 demo**：8 MCP Dockerfile、`deploy/docker-compose.prod.yml`、nginx DMZ 已落地，TLS 双路径正在推进。

---

## 5 分钟上手

```bash
# 1. clone
git clone https://github.com/charliehzm/medharness.git
cd medharness

# 2. install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. customize (interactive wizard)
python tools/customize.py
# 会问：公司名 / 行业子类 / 模型偏好 / 部署环境

# 4. dry-run end-to-end（跑通示例 change）
bash dryrun_e2e_v2.sh

# 5. production 配置预览（8 MCP + nginx + 双网，不启动容器）
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production.example config

# dry-run 输出：
# ✅ Step 0-12 全部通过
# ✅ AUDIT_BUNDLE.tar.gz 已生成（含哈希链）
# compose config 输出：
# ✅ 9 services / 2 networks 可解析
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
L2 Harness  Orchestrator + 6 Sub-agent │ Tiered Memory │ 9 Hook │ 8 MCP（4 production + 4 stub）
─────────────────────────────────────────────────────────────────
L1 模型层   编码 / Review / 架构 / 医学长文 / 脱敏小模型 + 合规独立模型
```

详见 [docs/architecture/](docs/architecture/)。

---

## 8 MCP 当前状态

| MCP | 状态 | 作用 |
|---|---|---|
| `phi-detector` | production | PHI 检测，含中文医疗 recognizer、Presidio / RegexOnlyNlpEngine workaround |
| `desensitize` | production | PHI 脱敏与可逆加密封装，含 key provider 抽象 |
| `model-router` | production | 模型 allowlist、异构性、限流和路由门禁 |
| `audit-log` | production | hashchain / fallback audit 基础；ClickHouse 真集成留 v0.6+ |
| `ci-trigger` | stub | 后续 M4 落地 pipeline trigger |
| `internal-kb` | stub | 后续 M3 落地内部知识库 |
| `pm-bridge` | stub | 后续 M5 落地 Jira / 飞书桥接 |
| `vector-db` | stub | 后续 M4 落地 Milvus + BGE-M3 |

T9 已为 8 MCP 建立 Dockerfile；T10 已提供生产 Compose 拓扑。

---

## 与开源生态的关系

| 我们用什么 | 我们加什么 |
|---|---|
| [microsoft/presidio](https://microsoft.github.io/presidio/) | 中文医疗 recognizer + 31 fields.yml + 上下文规则 |
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 12 步 + 5 步双通道 SOP |
| [github/spec-kit](https://github.com/github/spec-kit) | verify / compliance gate / audit freeze 扩展 |
| [anthropics/skills](https://github.com/anthropics/skills) | 医疗专属 21+2 Skill |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 8 件医疗合规专属 MCP（4 production + 4 stub） |

**我们独有**（核心 IP）：
- 异构性强制 Compliance-Agent（厂商家族 + 完整 model_id 双校验）
- AUDIT_BUNDLE 哈希链 + 6 年审计留痕 / WORM 设计 + 配对销毁 KMS 契约
- 12+5 双通道 SOP
- 90 天督导 + 主理人接棒培训方法论
- PIPL + 健康医疗数据安全指南本土化合规层

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

## 生产化进展

- **T7**: prompt-injection 规则 detector + 4 gate 红队演练
- **T8**: 月度 red-team cron + recall gate
- **T9**: 8 MCP Dockerfile、build gate、Trivy 扫描、非 root 镜像
- **T10**: production Compose、双网、host volume、nginx DMZ
- **T11**: TLS 双路径、443、证书检查与 self-signed 默认（进行中，未合并）

这些叶子让项目从“流程和规范”推进到了“真正可部署的受控系统”。

---

## 社区版 vs 商业版

| 能力 | 社区版（Apache 2.0） | 商业版（Proprietary） |
|---|---|---|
| 6 层架构骨架 | ✅ | ✅ |
| 23 Skill + 6 Sub-agent | ✅ | ✅ |
| 8 MCP server（4 production + 4 stub，Docker / Compose 拓扑） | ✅ | ✅ |
| Hook 脚本（warn 默认） | ✅ | ✅ + block + 报警 |
| 31 fields.yml | ✅ 通用 | ✅ + 客户化字段 |
| 训练好的中文医疗 phi-detector | ❌ | ✅ |
| 托管 MCP 集群（KMS / WORM） | ❌ | ✅ |
| Dashboard SaaS | ❌ | ✅ |
| 24x7 合规事件 SLA | ❌ | ✅ |
| 1 对 1 督导 / 现场培训 | ❌ | ✅ |

详见 [docs/community-vs-commercial.md](docs/community-vs-commercial.md)。

---

## 路线图（12 个月）

```
M1-M3 (Q1)  MVP + Presidio 集成 + 早期用户接入
M4-M6 (Q2)  MCP 真集成 + 培训开源 + 商业版 + v1.0
M7-M9 (Q3)  国际化 + 标准化 + 大客户案例
M10-M12 (Q4) 商业完整 + 团队扩张 + v2.0
```

详见 [docs/roadmap.md](docs/roadmap.md)。

---

## 红线（任何 PR 必读）

1. **L4 PHI 永不裸入 prompt** — 含原始患者标识必须先经 `phi-desensitize`
2. **模型按 allowlist 路由** — 不允许直连境外公共 API
3. **审计全量记录** — 每次 tool / 模型 / Skill 调用必落 `mcp-audit-log`
4. **测试数据合规** — 禁止生产采样脱敏，强制走 `test-data-generation` 合成
5. **绕过 Hook = 合规违规** — 关 Hook 需双委员会签字

---

## 社区 / 联系

| 渠道 | 用途 | SLA |
|---|---|---|
| [GitHub Discussions](https://github.com/charliehzm/medharness/discussions) | 提问 / 想法 / 案例分享（已开 5 主题 thread） | 24h 内首次回复 |
| [GitHub Issues](https://github.com/charliehzm/medharness/issues/new/choose) | bug / feature / case study | 同上 |
| [GitHub Security Advisory](https://github.com/charliehzm/medharness/security/advisories/new) | **PHI 泄漏 / 合规漏洞**私密披露（**勿在 public issue 提**） | 2h（高敏） |
| 微信：`supernera`（maintainer 直联） | 个人沟通 / 早期客户接洽 / 行为准则上报 | 工作日 24h |

> 推荐**先开 [Discussion](https://github.com/charliehzm/medharness/discussions)**：可被搜索 + 后来者受益。私聊适合早期客户 / 合规深聊。

---

## 贡献 / 安全 / License

- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 安全漏洞披露：[SECURITY.md](SECURITY.md) （**勿在 public issue 提交合规 / 安全漏洞**）
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
