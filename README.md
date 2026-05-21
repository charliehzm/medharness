# MedHarness

> **Harness Engineering for Medical AI Coding**
>
> 一套面向医疗数据 SaaS / 数据中台公司的开源 AI Coding 落地体系。
> HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南 全部合规。
> 6 个月从"零散使用 Cursor"到"企业级、可审计、可演进"。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-CC_BY--SA_4.0-lightgrey.svg)](LICENSE-CC-BY-SA-4.0)
[![Status](https://img.shields.io/badge/Status-v0.1.0--alpha-orange.svg)](CHANGELOG.md)

---

## 适合谁

| 你是 | MedHarness 给你 |
|---|---|
| 10-50 人医疗数据 SaaS 技术负责人 | 6 个月落地的完整 SOP + 合规闸门 |
| 互联网医院技术团队 | 速度 / 合规双满足的 12+5 步双通道 |
| 医院信息部 AI 化项目 | 完整培训方法论 + 90 天督导 |
| 药企 CRO 数字化部 | AUDIT_BUNDLE 哈希链 + 6 年 WORM |

**不适合谁**：通用 SaaS（用 spec-kit）、医疗器械 SaMD（用 IEC 62304 工具链）、个人爱好者（项目过重）。

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

# 输出：
# ✅ Step 0-12 全部通过
# ✅ AUDIT_BUNDLE.tar.gz 已生成（含哈希链）
# ✅ 5 分钟内你拥有了一个完整的合规 AI Coding 工作流
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
```

详见 [docs/architecture/](docs/architecture/)。

---

## 与开源生态的关系

| 我们用什么 | 我们加什么 |
|---|---|
| [microsoft/presidio](https://microsoft.github.io/presidio/) | 中文医疗 recognizer + 31 fields.yml + 上下文规则 |
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 12 步 + 5 步双通道 SOP |
| [github/spec-kit](https://github.com/github/spec-kit) | verify / compliance gate / audit freeze 扩展 |
| [anthropics/skills](https://github.com/anthropics/skills) | 医疗专属 21+2 Skill |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 8 件医疗合规专属 MCP |

**我们独有**（核心 IP）：
- 异构性强制 Compliance-Agent（厂商家族 + 完整 model_id 双校验）
- AUDIT_BUNDLE 哈希链 + 6 年 WORM + 配对销毁 KMS
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

## 社区版 vs 商业版

| 能力 | 社区版（Apache 2.0） | 商业版（Proprietary） |
|---|---|---|
| 6 层架构骨架 | ✅ | ✅ |
| 23 Skill + 6 Sub-agent | ✅ | ✅ |
| 8 MCP server（v2 实现） | ✅ | ✅ |
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

### 当下（v0.1.0-alpha · M1）

| 渠道 | 用途 | SLA |
|---|---|---|
| [GitHub Discussions](https://github.com/charliehzm/medharness/discussions) | 提问 / 想法 / 案例分享（已开 5 主题 thread） | 24h 内首次回复 |
| [GitHub Issues](https://github.com/charliehzm/medharness/issues/new/choose) | bug / feature / case study | 同上 |
| 微信：`supernera`（maintainer 直联） | 个人沟通 / 早期客户接洽 | 工作日 24h |
| `hello@medharness.io` *(D-1 启用)* | 一般咨询 | 48h |
| `security@medharness.io` *(D-1 启用)* | PHI 泄漏 / 合规漏洞披露（**勿在 public issue 提**） | 2h（高敏） |
| `conduct@medharness.io` *(D-1 启用)* | 行为准则相关 | 24h |

> 推荐**先开 [Discussion](https://github.com/charliehzm/medharness/discussions)**：可被搜索 + 后来者受益。私聊适合早期客户 / 合规深聊。

### 后续

- **M3**（约 2 个月内）：上线**微信用户群**（实名 + 邀请制 + 上限 200）
- **M6**：上线**微信公众号**「医疗 AI Coding 工程实践」
- **M7+**：上线 **Discord 国际频道** + **LinkedIn 公司主页**

<!-- M3 群 QR 占位（建好后替换）
![加入用户群](docs/img/community-wx-group.png)
群 QR 每周一更新（防 spam），扫码失败可在 Discussions 留言。
-->

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
