# 课件 06 · Skill Owner 培训

> 时长：60 分钟
> 受众：被选为 Skill Owner 的 Senior / QA / Architect
> 前置：课件 01-05

---

## 学习目标

- 知道 Skill Owner 的职责边界
- 学会读 routing-evals.json 评估 Skill 触发命中率
- 能完成一次 SKILL.md 季度审计

---

## 1. Skill Owner 制度（10 min）

每个 Skill 有一个 owner。
**不是开发该 Skill 的人**，是负责该 Skill **持续健康**的人。

### 职责

- 季度审计 description / trigger / 命中率
- 维护 references / templates / examples
- 跟踪 false positive / false negative 案例
- 跨季度迭代 routing-evals.json

### KPI

- Skill 触发准确率 ≥ 90%
- 被引用任务成功率 ≥ 85%
- 触发后 deprecation rate（被用户跳过率）≤ 10%

---

## 2. 怎么成为 Skill Owner（5 min）

不是任命，是**生长**：

1. 提 5 个该 Skill 相关 merged PR
2. 在 Discussions 申请，maintainer 批准
3. 加到 `governance/Skill-Owner-名册.md`（M2 后启用）

收益：
- 邮箱 alias：`<skill>@medharness.io`
- repo `CODEOWNERS` 里 owns 该 Skill 目录
- 该 Skill 改动 PR 自动 @ 你
- 行业声誉

---

## 3. 季度审计流程（20 min · 主要工作）

### Step 1 · 收集数据

```bash
# 看本季度该 Skill 被触发了多少次
cat .audit/skill_invocations.jsonl | jq 'select(.skill=="my-skill")' | wc -l

# 看命中 / 失败
cat .audit/skill_invocations.jsonl | jq 'select(.skill=="my-skill") | {success, reason}'
```

### Step 2 · 读 routing-evals.json

```bash
cat .claude/skills/<my-skill>/routing-evals.json
```

字段：
- `version` · 版本号（v1.x-v2.x）
- `_note` · 上次调优的说明
- `cases` · 触发样例
  - `prompt` · 用户 prompt
  - `expected_skill` · 应该触发的 Skill
  - `actual_skill` · 实际触发的（v1 测的）
  - `outcome` · success / wrong_skill / not_triggered

### Step 3 · 找症结

- 命中率 < 90% → description 模糊 / trigger 太宽
- 误触发率 > 10% → 与其他 Skill 重叠
- not_triggered 多 → trigger 太窄 / 用户写法没覆盖

### Step 4 · 改 SKILL.md

针对症结改三段：
- **description**：更准的"我干啥 / 我不干啥"
- **When to use**：补漏 trigger 例子
- **Workflow**：如步骤被跳过，强化第一步

### Step 5 · 跑红队 + 验证

```bash
bash tests/red-team-drills/run_all.sh
pytest tests/integration -v
```

新版本提 PR → 双 reviewer review（你 + 另一个 Skill Owner）→ merge。

---

## 4. 真实案例：PRD 系列 4 → 2 合并（10 min）

v2.0 我们有 4 个 PRD Skill：
- `prd-precheck` / `prd-implementation-precheck`
- `prd-author` / `prd`

实测**开发者 70% 选错**。

**症结**：description 不区分，trigger 90% 重叠。

**修法**：
1. 合并：`prd-precheck` → alias `prd-implementation-precheck`
2. 合并：`prd-author` → alias `prd`
3. alias 文件保留兼容（标 deprecated）

**结果**：
- 误选率 70% → < 5%
- SKILL 总数 25 → 23

教训：**Skill 多不如少**。Owner 该砍就砍。

---

## 5. routing-evals.json 实例（5 min）

```json
{
  "version": "1.1-v2.2",
  "_note": "v2.2 调优：v2.1 实测手动触发率 8%。本版改为 trigger 关键词加权 + 60s 缓存。",
  "cases": [
    {
      "prompt": "review my code",
      "expected_skill": "requesting-code-review",
      "v1_actual": "systematic-debugging",
      "outcome": "wrong_skill",
      "fix": "description 加 'this is for code review, not debugging'"
    },
    {
      "prompt": "找一下这段代码的 bug 根因",
      "expected_skill": "systematic-debugging",
      "v1_actual": "systematic-debugging",
      "outcome": "success"
    }
  ]
}
```

每个季度跑一次，cases 累积 ≥ 50 条。

---

## 6. Owner 之间的协作（5 min）

- 月度 owner 例会（30 min · 同步）
- 跨 Skill 改动必通知相关 owner
- Owner 离职 / 长假 → 提前 1 月找接班

记录在 [governance/Skill-Owner-名册.md] 私有备份（M2 后开放部分公开）。

---

## 7. 课后作业

1. 选 1 个你想 own 的 Skill
2. 读完该 Skill 的 SKILL.md + routing-evals.json（如有）
3. 在 Discussions 发"我想 own X Skill，已有 N 个相关 PR"
4. 完成 [07-新人入职清单.md](07-新人入职清单.md)

---

## 自检

- [ ] 我知道 Skill Owner 不是写代码，是持续维护
- [ ] 我能跑季度审计 5 步
- [ ] 我会读 routing-evals.json
- [ ] 我知道"Skill 多不如少"的原则
