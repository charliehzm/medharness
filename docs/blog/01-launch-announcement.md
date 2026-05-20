# 医疗 AI Coding 落地：开源 MedHarness 项目立项书

> 首发渠道：微信公众号 / 知乎 / V2EX
> 字数：约 3000 字
> 立项日期：2026-05-19

---

## 引子

过去一年我在一家 30 人的医疗数据 SaaS 公司全程主导了 AI Coding 落地，
经历了三个版本（v2.0→v2.1→v2.2）的演化：

- **v2.0** 刚上线：开发者 NPS = 18，Hook 误判率 66%，AUDIT_BUNDLE 87MB（一次审计要 4 小时）
- **v2.1** 改完审计：补完 24 项 🔴 阻断级缺陷
- **v2.2** 提速：micro 通道、phi-detector v3、Compliance-Agent 异构强制 …… 最终 NPS 40+

这一年总结的 4 件关键事：

1. **合规闸门必须前置**，等出事再补就晚了
2. **异构性强制**，Compliance-Agent 模型必须与 Coder 不同厂商，否则"自证清白"
3. **培训方法论比工具重要**，90 天督导 + 主理人接棒，否则团队不成熟体系起不来
4. **Hook 误判要降到 15% 以下**，不然开发者一周后就关掉了

这些经验在公司内部已经闭环。但今天我决定把它开源——叫 **MedHarness**。

---

## 为什么开源

第一个原因：**业界第一次能看见医疗 AI Coding 的真实演化代价**。

主流的开源 AI Coding 项目（spec-kit / OpenSpec / Claude Code skills）都是通用工具。
医疗领域差异很大：

- HIPAA 18 标识符 + PIPL + 数据安全法的合规边界
- PHI 永不裸入 prompt 的工程纪律
- 6 年 WORM 审计可重放
- 异构性 Compliance-Agent 强制

这些不是工具能解决的，是**研发体系**问题。我们用了一年的演化把这套体系跑通——如果只是公司内部用，能让 30 个人受益；如果开源，能让 3000 个工程师不再踩同样的坑。

第二个原因：**站在巨人肩膀上**。

MedHarness 不重造轮子，而是垂直在医疗：

| 层 | 我们 vendor | 加什么 |
|---|---|---|
| PHI 检测 | [microsoft/presidio](https://microsoft.github.io/presidio/) | 中文医疗 recognizer + 31 fields.yml |
| Spec 框架 | [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 12 步主通道 + 5 步 micro |
| Spec 三段式 | [github/spec-kit](https://github.com/github/spec-kit) | verify / compliance gate / audit freeze |
| MCP 框架 | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 8 件医疗专属 server |
| Skill 设计 | [anthropics/skills](https://github.com/anthropics/skills) | 23 医疗专属 Skill |

我们的核心 IP（无开源替代）是：

1. **12 步 + 5 步双通道 SOP**
2. **异构性强制 Compliance-Agent**
3. **AUDIT_BUNDLE 哈希链 + 6 年 WORM**
4. **三视角穿透审计法**
5. **M1-M6 沙盘模拟法**
6. **routing-evals.json 反哺机制**
7. **90 天督导 + 主理人接棒培训**
8. **PIPL + 健康医疗数据安全指南** 本土化合规层

---

## 适合谁 · 不适合谁

### 适合

- 10-50 人医疗数据 SaaS / 数据中台 / 互联网医院 / 药企 CRO
- 已经在用 Cursor / Claude Code，但**没有合规闸门**
- 准备过监管 / 客户审计

### 不适合

- 通用 SaaS 公司 → 用 spec-kit 就够
- 非中国 + 非美国市场 → 合规层不适用
- 医疗器械软件 SaMD → 那是 IEC 62304 工具链
- 个人 hobbyist → 项目重，1 人撑不起

---

## 6 个月你能拿到什么

```
M1  跑通 12 步 SOP 一次（先锋小组 3-5 人）
M2  L5 合规层 + 3 个核心 MCP 上线
M3  Compliance-Agent + WORM 审计闭环
M4  MCP 8 件套全部稳定
M5  全员推广 + 培训方法论
M6  KPI 上线 + Verify ≥ 75% + PHI 漏出 = 0 + 审计可重放 100%
```

如果你照着 [研发交付SOP-v2.md](../../研发交付SOP-v2.md) 走，**6 个月可量化交付**。

---

## 项目边界（明确不做的事）

| 不做 | 理由 |
|---|---|
| 通用 AI Coding 工具 | spec-kit 已做 |
| PHI 检测库 | Presidio 已工业级 |
| 新 LLM 框架 | LangChain / LlamaIndex 红海 |
| 医疗器械软件 SaMD | IEC 62304 另一套法规 |
| 实时监控 AIOps | 传统 AIOps 不是强项 |

只做**"医疗 SaaS 的 AI Coding 落地全套体系"**——这一个垂直点。

---

## 商业模式：Open-Core

类似 GitLab / Sourcegraph / Mattermost：

| 社区版（Apache 2.0） | 商业版（Proprietary） |
|---|---|
| 6 层架构骨架 | 训练好的 phi-detector 模型权重 |
| 23 Skill + 6 Sub-agent | 托管 MCP 集群 + 真 KMS + WORM |
| 8 MCP server v2 | Dashboard SaaS |
| 9 Hook（warn 默认） | 24x7 合规事件 SLA |
| 31 fields.yml | 1 对 1 督导 + 现场培训 |
| 完整培训方法论 | 客户化字段 / 合同 / 法务模板 |

**License 永久承诺**：已发布的社区版组件，license 永久 Apache 2.0 / CC BY-SA 4.0。
不会效仿 MongoDB / Elastic 改 SSPL / BSL。

---

## 12 个月路线图

```
Q1 (M1-M3)   MVP + Presidio + 第一批早期用户
Q2 (M4-M6)   完整 MCP + 培训开源 + 商业版 + v1.0
Q3 (M7-M9)   国际化 + 标准化 + 大客户案例
Q4 (M10-M12) 商业完整 + 团队扩张 + v2.0
```

目标 12 月：GitHub stars 2000 + 30 家用户 + 8-10 家付费客户。

---

## 立即上手

```bash
git clone https://github.com/charliehzm/medharness.git
cd medharness
bash dryrun_e2e_v2.sh
```

5 分钟拿到一个跑通的合规 AI Coding 工作流 + AUDIT_BUNDLE.tar.gz。

---

## 我希望从你那里得到什么

如果你是：

- **医疗 SaaS 工程师** → 帮我跑 dryrun，反馈是否真的"5 分钟上手"
- **公司技术负责人** → 帮我看 12 步 SOP 是否你能用
- **Compliance Officer / 法务** → 看合规层是否符合你认知的边界
- **开源贡献者** → 看 [CONTRIBUTING.md](../../CONTRIBUTING.md)，第一个 PR 我会真诚感谢
- **媒体 / 行业** → 看 [README.md](../../README.md)，欢迎引用 / 报道

---

## 一句话愿景

> **5 年后，所有想用 AI Coding 的医疗数据 SaaS 公司，第一周必须先 fork MedHarness。**

---

## 链接

- GitHub：https://github.com/charliehzm/medharness
- 文档：https://medharness.dev
- 微信群（用户）：见 README
- 邮箱：hello@medharness.io

---

> *本博客本身按 CC BY-SA 4.0 授权。欢迎转载，保持署名 + 同许可。*
> *作者：MedHarness Maintainers · 2026-05-19*
