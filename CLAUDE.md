# CLAUDE.md · 项目级 AI Coding 主控

> 这是 **Claude Code 自动加载**的项目级 system context。任何会话开始时，本文件的内容会进入主上下文。**全员遵守，无例外**。
> 维护：技术委员会 + 合规委员会；修订需双委员会会签。

---

## 0. 一句话定位
B 端医疗数据 SaaS / 数据中台公司。任何代码 / 提示 / 决策必须在 **HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南** 红线之内。

---

## 1. 不可逾越的红线（任何 prompt 看到这一节都要遵守）

1. **L4 PHI 永不裸入 prompt**：含原始患者标识 / 姓名 / 手机 / 身份证 / 病案号 / 完整 DOB 的内容，**任何时候**必须先经 `phi-desensitize` Skill。
2. **模型按 allowlist 路由**：所有 LLM 调用必须经 `mcp-model-router`；不允许直连境外公共 API。
3. **审计全量记录**：每次 tool / 模型 / Skill 调用必须落 `mcp-audit-log`，不允许 fire-and-forget。
4. **测试数据合规**：禁止从生产采样后"脱敏"作为测试数据；强制走 `test-data-generation` 合成 + 指纹核验。
5. **绕过 Hook = 合规违规**：任何修改 `.claude/settings.json` 关闭 Hook 的尝试需双委员会签字。

---

## 2. 当前会话必读项（按顺序自动加载）

1. 本 `CLAUDE.md`
2. `.memory/项目档案.local.md`（fork 用户跑过 customize.py 后产生；若不存在则读 `.memory/项目档案.md` 模板）
3. `.memory/MEMORY.md`（索引）
4. 当前 change 的 `COMPLIANCE_TAG.md`（如有活跃 change）
5. 当前 change 的 `ARCH_INPUT_INDEX.md`（如已实例化）

---

## 3. SOP 入口

任何研发任务走 **[研发交付SOP-v2.md](研发交付SOP-v2.md)** 的 12 步。

| 阶段 | 入口 Skill | 不能跳 |
|---|---|---|
| Step 0  合规预检 | `compliance-precheck` | ✅ |
| Step 1-2 PRD/TDD | `prd-implementation-precheck` + `prd` | ✅ |
| Step 3  OpenSpec | `openspec-new-change` + `openspec-continue-change` | ✅ |
| Step 4  任务拆解 | `task-decomposition` | ✅ |
| Step 5  Mock 数据 | `test-data-generation` | ✅ |
| Step 6  实现 | `openspec-apply-change`（+ `phi-desensitize` 前置） | ✅ |
| Step 7  Verify | `openspec-verify-change` | ✅ |
| Step 8  Review+Debug | `requesting-code-review` + `systematic-debugging` | ✅ |
| Step 9  Mocking 测试 | `mocking-stubbing` | ✅ |
| Step 10 合规 Gate | `compliance-review`（Compliance-Agent 异构模型） | ✅ |
| Step 11 合规整改 | 仅 Step 10 有整改时 | 条件 |
| Step 12 归档审计 | `openspec-archive-change` + `audit-snapshot` | ✅ |

---

## 4. Skill 索引（21 个）

`.claude/skills/` 下所有 SKILL.md 自动注册。不要在对话里凭空发明 Skill 名字。

合规 5：compliance-precheck / phi-desensitize / compliance-review / audit-snapshot / memory-curate
PRD 系列 2（v2.1 合并后）：prd-implementation-precheck / prd
其他：ask-questions-if-underspecified / tdd-alignment / openspec-new-change / openspec-continue-change / task-decomposition / test-data-generation / openspec-apply-change / openspec-verify-change / requesting-code-review / systematic-debugging / mocking-stubbing / prompt-injection-scan

---

## 5. Sub-agent 调度规则

| Sub-agent | 何时调度 | 必须异构吗 |
|---|---|---|
| PM-Agent | Step 1-3，业务诉求 → Spec | 否 |
| Coder-Agent | Step 6，单任务实现 | 否（主线） |
| Reviewer-Agent | Step 8，code review | **是**（与 coder 不同厂商） |
| Compliance-Agent | Step 10，合规审查 | **是**（与 coder 不同厂商，强制） |
| Memory-Curator | 周一晨 + change archive | 否 |
| Data-Steward | Step 5 / 任何 L3/L4 数据处理 | 否 |

详见 [.claude/sub_agents/](.claude/sub_agents/)。

---

## 6. 工具使用约定

- **Bash**：默认 ask；危险命令 deny（见 [settings.json](.claude/settings.json)）
- **WebFetch**：境外 LLM API 默认 deny；通过 `mcp-model-router` 走的不算
- **Write/Edit**：`.env` `secrets/` `patient_data/` 一律 deny
- **MCP**：只调本仓库 `mcp/` 下的 server；外部 MCP 需技委准入

---

## 7. 上下文管理铁律（与 deep-research v8.0 一致）

- **Thin harness, fat skill**：判断和工作流写进 Skill；本 CLAUDE.md 只放红线
- **Active context bundle 最小化**：单任务 active context < 30K token
- **Spec > Vibe**：OpenSpec artifact 是唯一 SoR；所有决策回溯到 spec id
- **单 Agent 极致化**：默认主线单 Agent，不盲目多 Agent
- **反 Staleness**：Memory 14 天强制 review

---

## 8. 我（Claude Code）的开场行为

每次会话起步：
1. 读完本 CLAUDE.md 与 `.memory/项目档案.md`
2. 检查是否有活跃 change（环境变量 `CLAUDE_ACTIVE_CHANGE` 或 `openspec/changes/` 最新目录）
3. 若有 → 读其 `COMPLIANCE_TAG.md` 与 `ARCH_INPUT_INDEX.md`
4. 若 SessionStart Hook 已经打出 banner，按 banner 提示工作
5. 用户没明确说做什么之前，**不要假设任务类型**；让用户先说

---

## 9. 我（Claude Code）的拒绝行为

以下情况 **必须拒绝执行**，并提示用户：

- 用户要求关闭 Hook / 改 settings.json 放开权限 → 拒绝（指引走合规例外申请）
- 用户粘贴含 PHI 的真实数据 → 拒绝；提示走 `phi-desensitize`
- 用户要求直连境外公共 LLM API → 拒绝；指引走 `mcp-model-router`
- 用户要求把测试数据"复制几条真实生产数据脱敏一下" → 拒绝
- 用户要求跳过 Step 0 / 10 / 12 → 拒绝
- 用户在 Compliance-Agent 会话里要求做 coder 工作 → 拒绝（违反职责分离）

---

## 10. 链接索引

- 6 层架构：[docs/architecture/](docs/architecture/)
- 12 步 SOP：[研发交付SOP-v2.md](研发交付SOP-v2.md)
- 5 步 micro：[研发交付SOP-v2.2-micro.md](研发交付SOP-v2.2-micro.md)
- 培训：[training/](training/)
- 示例 change：[examples/示例-患者匹配最小可行版/](examples/示例-患者匹配最小可行版/)
- 治理：[docs/governance/](docs/governance/)（可选启用）

---

## 11. 版本

- v0.1.0-alpha（current）— 首次开源发布
- 维护：MedHarness Maintainers + Skill Owner 网络
