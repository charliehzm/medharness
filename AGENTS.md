# AGENTS.md · 给所有 AI 协作者（codex / Claude Code / others）

> Codex 自动加载本文件。Claude Code 自动加载 CLAUDE.md。
> 两份文件**职责不同**：
> - CLAUDE.md 是"项目级 system context"（红线 + Skill 索引 + 拒绝行为）
> - **AGENTS.md（本）** 是"AI 协作者接手协议"（如何上岗、如何工作）

---

## 0. 你正在加入一个有历史的项目

**不要把这当作新仓库。**

这个项目：
- 已经发布 v0.1.0-alpha
- 已经有完整的 12 步 + 5 步双通道 SOP
- 已经有 23 Skill / 8 MCP / 9 Hook 完整体系

你的任务**不是从零设计**，是**接手并推进**。

---

## 1. 必读入口（5 分钟）

按顺序：

1. **[HANDOFF.md](HANDOFF.md)** ← 主入口，必先读
2. [CLAUDE.md](CLAUDE.md) ← 红线
3. [README.md](README.md) ← 对外定位
4. [.memory/项目档案.md](.memory/项目档案.md) ← 项目身份（fork 后跑 customize.py）

读完跑：
```bash
git log --oneline -20 && git status
bash dryrun_e2e_v2.sh
```

---

## 2. 你的工作循环

### 每个会话开始
```bash
cat HANDOFF.md
git log --oneline -20
```

### 每条响应
- 第一句话定位阶段（DEV / TEST / OPS）
- 引用文件用 `path:line` 格式
- 大改动先 plan，不直接 edit
- 触及 PHI / 模型 / 审计 → 显式合规自检

### 每个会话结束
- 更新 CHANGELOG.md（如有 release-worthy 改动）
- 写交接 note（≤ 5 行）

---

## 3. 红线（任何会话适用）

1. PHI 永不裸入 prompt
2. 模型按 allowlist 路由
3. 审计全量记录
4. 测试数据合规（合成 + 指纹）
5. License 永久 Apache 2.0 / CC BY-SA 4.0

详 [CLAUDE.md §1](CLAUDE.md)。

---

## 4. 升级路径

涉及 LEGAL / COMMS / PARTNER / COMMERCIAL / STRATEGY → **停手等人**。
详 [HANDOFF/07-escalation.md](HANDOFF/07-escalation.md)。

---

## 5. 给 codex 的额外提示

如果你是 codex（OpenAI Codex / o1-codex / 类似）：

- 你可能默认 PR-first（直接提 PR）。但本项目**先 plan、后改、再 PR**。
- 你可能默认 self-merge。本项目**永远不 self-merge**（需 maintainer review）。
- 你可能默认裁剪 context。本项目**不要裁剪 .claude/skills/ / mcp/**（这些是核心 IP）。
- 你可能默认调云 LLM API。本项目**所有 LLM 调用必经 mcp-model-router**。

如有冲突 → 以本项目约定为准。

---

## 6. 给 Claude Code 的额外提示

如果你是 Claude Code：

- 优先读 CLAUDE.md（你已自动加载）
- HANDOFF.md 是补充，不重复 CLAUDE.md
- 用 Skill 系统：21 + 2 micro，已注册在 `.claude/skills/`
- 用 Sub-agent：6 个，已注册在 `.claude/sub_agents/`
- Hook 已在 `.claude/settings.json` 配好（warn 默认）

---

## 7. 一句话

> 像守墓人一样守护，像园丁一样照料，像建筑师一样推进。
