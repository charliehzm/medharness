# HANDOFF · 新会话 / 新 fork 协作者接手必读

> 你拿到这份文档，意味着你是 MedHarness 的下一位协作者（fork 维护者 / AI 协作 agent / 接手 maintainer）。
> 这份文档让你在 5 分钟内 ramp up，并避开最容易踩的坑。

---

## 0. 5 分钟必读

按顺序：

1. **本 HANDOFF.md** — 你正在读
2. **[AGENTS.md](AGENTS.md)** — AI 协作者约定（codex / Claude Code 通用）
3. **[CLAUDE.md](CLAUDE.md)** — 项目级红线
4. **[README.md](README.md)** — 项目对外定位
5. **[.memory/项目档案.md](.memory/项目档案.md)** — 项目身份（fork 后请跑 `python tools/customize.py`）

读完跑：
```bash
git log --oneline -20
git status
bash dryrun_e2e_v2.sh
```

---

## 1. 项目一句话

**MedHarness · 医疗 SaaS 公司的开源 AI Coding 落地体系。HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南。Apache 2.0 + CC BY-SA 4.0。永久开源承诺。**

---

## 2. 你是谁

如你是：
- **fork 这个仓库的维护者** → 你打算用它在你公司落地 AI Coding 体系
- **AI 协作者**（codex / Claude Code 等）→ maintainer 让你接手开发 / 测试 / 运营某一段
- **接手 maintainer**（项目转交 / 长假回归）→ 你需要快速接续工作

无论哪种身份，本文档 + 5 红线 + SOP 是你的护栏。

---

## 3. 不可逾越的 5 条红线

| # | 红线 | 违反后果 |
|---|---|---|
| R1 | **L4 PHI 永不裸入 prompt**（必先经 `phi-desensitize` Skill） | 监管处罚 |
| R2 | **模型按 allowlist 路由**（必经 `mcp-model-router`，不直连境外公共 API） | 合规违规 |
| R3 | **审计全量记录**（每次 tool/模型/Skill 调用必落 `mcp-audit-log`） | 监管无法重放 |
| R4 | **测试数据合规**（禁止生产采样脱敏，强制 `test-data-generation` 合成） | 反演风险 |
| R5 | **不改 License**（永久承诺 Apache 2.0 + CC BY-SA 4.0） | 社区信任崩盘 |

任何 PR / 任何 commit / 任何决策 → 自检 5 条。

---

## 4. 三阶段使命

| 阶段 | 含义 |
|---|---|
| **DEV** | 按 SOP（12 步主通道 / 5 步 micro 通道）推进 change |
| **TEST** | 单测 + 集成测试 + 月度红队演练 + 季度流程回放 |
| **OPS** | 24h 内回复 Issues/Discussions + 持续内容产出 + 社区运营 |

每个会话**先定位**当前在哪个阶段。

---

## 5. 每个会话的 ritual

### 5.1 会话开始（前 3 分钟）

```bash
git log --oneline -20
git status
cat .memory/项目档案.md
```

### 5.2 响应规范

- **第一句话定位**："这是 DEV / TEST / OPS 哪个阶段"
- **引用文件**：用 `path/to/file.md:42` 格式，不 vague reference
- **大改动先 Plan**：> 50 行 / 跨多文件 → 先写 plan 等用户确认
- **合规自检**：触及 PHI / 模型 / 审计 → 显式写"已自检红线 R1-R5"

### 5.3 会话结束（最后 3 分钟）

- **更新 [CHANGELOG.md](CHANGELOG.md)** 如有发布意义的变更
- **写交接 note** 给下次会话（≤ 5 行）
- **commit** 如有改动（用户授权后）

---

## 6. 你**不**能做的事

- ❌ 改 LICENSE 收紧（永久承诺）
- ❌ 跳过 SOP 直接写代码（micro 通道也是 5 步 SOP）
- ❌ 把 Compliance-Agent 切回与 Coder 同模型（异构性强制）
- ❌ 删 Hook / 关 Hook（双委员会签字才可）
- ❌ 合并 PHI 与非 PHI 字段到同一变量名
- ❌ 公开发声（Twitter / 公众号 / 论坛）—— 内容你写 draft，但发布是 maintainer
- ❌ 与外部第三方签合同 / 申请合规认证 / 注册商标

---

## 7. 升级路径（你做不了的时候）

| 情景 | 处理 |
|---|---|
| 涉法律 / 合规边界 | 标 🚨 LEGAL，停手等 maintainer + 律师 |
| 涉公开发声 / 媒体 | 标 🎙️ COMMS，写 draft 不发 |
| 涉外部合作 / 联盟 | 标 🤝 PARTNER，列建议不联系 |
| 涉商业谈判 / 报价 | 标 💰 COMMERCIAL，停手 |
| 决策权超 D 级改动 | 标 🧭 STRATEGY，写 RFC 等签字 |
| 不确定是否越权 | **默认停手** + 标 ❓UNCERTAIN |

详 [HANDOFF/07-escalation.md](HANDOFF/07-escalation.md)。

---

## 8. 7 个最容易踩的坑

| # | 坑 | 怎么避 |
|---|---|---|
| 1 | 忘记项目是医疗，把 PHI 当普通数据 | 任何 sample data 先问"这是 L1-L4 哪一级" |
| 2 | 凭空发明新决策 / 改红线 | 任何决策改动必走 RFC 流程（CONTRIBUTING.md） |
| 3 | 跳过 SOP 直接写代码 | 任何代码改动必关联一个 OpenSpec change |
| 4 | 改 License 收紧 | 永久承诺。任何改 LICENSE 文件的 PR 自动拒绝 |
| 5 | 让 Compliance-Agent 和 Coder 用同一个模型 | 启动 `customize.py` 会拦；手动配置时自检异构性 |
| 6 | AUDIT_BUNDLE 缺哈希链 | 跑 `audit-snapshot` Skill，不要手搓 tar |
| 7 | Issue / Discussion 24h 未回 | 每个会话先扫一遍未回项 |

---

## 9. 工具速查

| 任务 | 工具 |
|---|---|
| 跑端到端 SOP | `bash dryrun_e2e_v2.sh` |
| 客户化（fork 后第一件事） | `python tools/customize.py` |
| 红队演练 | `bash tests/red-team-drills/run_all.sh` |
| 测试 | `pytest tests/ -v` |
| Lint | `ruff check . && ruff format .` |

---

## 10. 完整文档地图

- [CLAUDE.md](CLAUDE.md) · Claude Code 自动加载（红线 + Skill 索引）
- [AGENTS.md](AGENTS.md) · codex 自动加载（AI 协作者协议）
- [研发交付SOP-v2.md](研发交付SOP-v2.md) · 12 步主通道 SOP
- [研发交付SOP-v2.2-micro.md](研发交付SOP-v2.2-micro.md) · 5 步 micro 通道 SOP
- [CONTRIBUTING.md](CONTRIBUTING.md) · 贡献指南（含 RFC 流程）
- [SECURITY.md](SECURITY.md) · 合规漏洞披露通道
- [HANDOFF/01-system-prompt.md](HANDOFF/01-system-prompt.md) · AI 启动 prompt 模板
- [HANDOFF/06-self-check-protocol.md](HANDOFF/06-self-check-protocol.md) · 三层自检 protocol
- [HANDOFF/07-escalation.md](HANDOFF/07-escalation.md) · 6 类升级路径
- [examples/示例-患者匹配最小可行版/](examples/示例-患者匹配最小可行版/) · 完整 change 示例

---

## 11. 一句话

> 这不是你从零做的项目，是你**继承**的项目。
> 守红线、走 SOP、回 issue。
>
> 慎之，慎之。
