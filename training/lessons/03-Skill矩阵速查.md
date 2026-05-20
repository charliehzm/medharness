# 课件 03 · Skill 矩阵速查（23 个 Skill）

> 时长：45 分钟
> 受众：会写 PR 的人
> 前置：课件 01-02

---

## 学习目标

- 知道 23 个 Skill 各自什么时候触发
- 学会读 SKILL.md 的三段式
- 避开"PRD 系列 70% 误选率"的坑

---

## 1. Skill 是什么（5 min）

Skill = `.claude/skills/<name>/SKILL.md`。

每个 SKILL.md 含三段：

```yaml
---
name: <skill-name>
description: 一句话说清"它干啥 / 什么时候用"
---

## When to use
（触发场景，trigger 关键词）

## Workflow
（具体步骤）

## References
（外部链接 / 模板）
```

**触发机制**：Claude Code 看到上下文匹配 description / when-to-use → 自动调用。
不需要手动 `/skill xxx`（但可以）。

---

## 2. 23 个 Skill 矩阵（25 min）

### 合规 5（红线相关，所有 change 必经）

| Skill | 触发 | 产物 |
|---|---|---|
| `compliance-precheck` | Step 0 / 新需求 | COMPLIANCE_TAG.md + MODEL_ALLOWLIST.json |
| `phi-desensitize` | 任何接触医疗字段 | 脱敏文本 + 反向映射表 |
| `compliance-review` | Step 10 | COMPLIANCE_REPORT.md |
| `audit-snapshot` | Step 12 | AUDIT_BUNDLE.tar.gz + 哈希链 |
| `memory-curate` | 每周 + change archive | 刷新 / 合并 / 失效报告 |

### PRD 系列 2（v2.1 合并后）

| Skill | 触发 | 产物 |
|---|---|---|
| `prd-implementation-precheck` | Step 1 | PRD 缺口清单 |
| `prd` | Step 2 | PRD.md（含 ../../docs 引用） |

**注意**：以前有 4 个 PRD 系列 Skill，开发者 70% 选错。v2.1 合并为 2 + 2 alias（保留兼容老 SOP）。
**不要**用 `prd-author` / `prd-precheck`（alias，已标 deprecated）。

### 通用 SOP 8

| Skill | 触发 | 产物 |
|---|---|---|
| `ask-questions-if-underspecified` | 任意阶段需求不明 | 问题清单 |
| `tdd-alignment` | Step 3 | 测试用例骨架 |
| `openspec-new-change` | Step 4（新 change） | proposal / design / specs / tasks |
| `openspec-continue-change` | Step 4（继续既有） | 增量 spec |
| `task-decomposition` | Step 5 | 任务列表（≤ 2 文件/任务） |
| `test-data-generation` | Step 6 | 合成测试数据（带指纹） |
| `openspec-apply-change` | Step 7 | 代码 diff |
| `openspec-verify-change` | Step 8 | Verify 报告 |

### 调试 / Review / Mock 4

| Skill | 触发 | 产物 |
|---|---|---|
| `requesting-code-review` | Step 9 | review 任务包 |
| `systematic-debugging` | bug 触发 | 根因 + 修复计划 |
| `mocking-stubbing` | 联调阶段 | mock 实现 + 测试结果 |
| `prompt-injection-scan` | RAG / 外部知识库接入 | 注入风险报告 |

### micro 2 + quick 1

| Skill | 触发 | 产物 |
|---|---|---|
| `audit-snapshot-micro` | 5 步 micro 通道 Step 5 | 简化 AUDIT_BUNDLE |
| `quick-fix` | ≤ 2 文件改动 | 自动判断 + 路由 micro / 12 步 |

---

## 3. 怎么读 SKILL.md（10 min · 实操）

打开 `.claude/skills/compliance-precheck/SKILL.md`：

```bash
cat .claude/skills/compliance-precheck/SKILL.md | head -40
```

**逐段过**：
1. frontmatter（name / description）
2. When to use（trigger 场景）
3. Workflow（具体步骤）
4. References（链接）

练习：选一个 Skill 自己读完，能回答：
- 它在什么场景触发？
- 它的产物是什么？
- 它依赖哪些上游 Skill？

---

## 4. routing-evals.json（Skill Owner 才看，5 min）

部分 Skill 有 `routing-evals.json` 文件：
- 记录"过去 N 次被触发"的成功 / 失败案例
- Memory-Curator 周一扫一次
- Skill Owner 每季度 review → 更新 description / trigger

这是**Skill 触发准确率持续 evolve** 的机制。

---

## 5. 课后作业

1. 选 1 个 Skill 通读 SKILL.md
2. 在 Discussions #3 提一个"我对 XXX Skill 的疑问"
3. 下次课前完成 [04-合规Hook与PHI防护.md](04-合规Hook与PHI防护.md)

---

## 自检

- [ ] 我能列出 23 个 Skill 的名字（至少 20 个）
- [ ] 我知道 PRD 系列只用 2 个、不用 alias
- [ ] 我能在 30 秒内找到任一 Skill 的 SKILL.md
- [ ] 我会读 SKILL.md 三段式
