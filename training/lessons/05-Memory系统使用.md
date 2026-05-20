# 课件 05 · Memory 系统使用

> 时长：45 分钟
> 受众：会写 PR 的人
> 前置：课件 01-04

---

## 学习目标

- 知道 Memory artifact 的 5 种类型
- 理解 fact vs inference 区别
- 学会跑 memory-curate Skill 清理 staleness

---

## 1. Memory 不是 Context（5 min）

| | Context（上下文） | Memory（记忆） |
|---|---|---|
| 范围 | 当前会话 | 跨会话持久 |
| 大小 | < 30K token / change | 累积成长 |
| 存放 | Claude 内存 | `.memory/` 目录 |
| 失效 | 会话结束 | 14 天 staleness review |

Memory 解决"下个会话还得知道这件事"问题。

---

## 2. 5 种 Memory artifact（15 min）

```
.memory/
├── MEMORY.md                    ← 索引（自动加载）
├── 项目档案.md                   ← 占位模板
├── 项目档案.local.md            ← customize.py 写入（gitignored）
└── templates/
    ├── PRD_SUMMARY.template.md
    ├── PROTOTYPE_SUMMARY.template.md
    ├── ARCH_INPUT_INDEX.template.md
    ├── LEGACY_FACTS.template.md
    └── LEGACY_INFERENCES.template.md
```

| 类型 | 用途 | 产出时机 |
|---|---|---|
| **项目档案** | 项目身份 / 红线 / 当前阶段 | customize.py 一次性 |
| **PRD_SUMMARY** | PRD 摘要（≤ 2KB） | Step 2 |
| **PROTOTYPE_SUMMARY** | spec 摘要（关键决策 + 接口） | Step 3-4 |
| **ARCH_INPUT_INDEX** | 实现前的"既有上下文索引" | Step 6 前 |
| **LEGACY_FACTS** | 既有代码 / 业务**事实**陈述 | 持续累积 |
| **LEGACY_INFERENCES** | 既有代码 / 业务**推断**陈述（含 derives_from） | 持续累积 |

---

## 3. LEGACY_FACTS vs LEGACY_INFERENCES（10 min · **核心区别**）

### FACTS（可立刻验证）

```markdown
| 事实 | 来源 |
|---|---|
| 字段 `patient_name` 是 VARCHAR(200) | db/migrations/0023.sql:12 |
| v2.0 关 Hook 那次是 PR #142 | git log --grep="hook" |
```

✅ 可 grep / git blame / 数据库 query 直接确认。

### INFERENCES（基于事实推断 + 假设）

```markdown
| 推断 | derives_from | 置信度 | 过期条件 |
|---|---|---|---|
| 字段 200 chars 是为了复姓 + middle name | LEGACY_FACTS#L7 + email-2025-09-12 | 中 | 如发现实际只用 50 chars |
```

⚠️ **必含 derives_from + 置信度 + 过期条件**。

### 为什么分开？

事实不过期。推断会过期。
混在一起 → 项目老了，推断错了你不知道，仍当事实用 → 错误决策。

---

## 4. memory-curate Skill（10 min · 实操）

### 4.1 周一晨跑一次

```bash
# 在 Claude Code 里直接说："跑一下 memory-curate"
# 或者 prompt：
# "Use the memory-curate Skill to review staleness of .memory artifacts"
```

### 4.2 它会做什么

1. 扫所有 .memory/*.md 的 last-modified
2. > 14 天没动 → 标 ⚠️ stale
3. LEGACY_INFERENCES 的 `过期条件` 触发了 → 标 🔴 expired
4. 产出周报（哪些要 review）

### 4.3 你的工作

收到周报：
- ⚠️ stale 项：花 30 秒 review → 还有效 → 修改日期 / 还无效 → 删
- 🔴 expired 项：必须处理 → 改 / 删 / 重写

**不处理 = 项目记忆腐烂**。

---

## 5. 实操（5 min）

```bash
cd /your/medharness/fork
ls -la .memory/
cat .memory/MEMORY.md
ls -la .memory/templates/

# 看一个模板
cat .memory/templates/PRD_SUMMARY.template.md
```

练习：在自己项目里，找一个你下周要做的 change，用 PRD_SUMMARY 模板写一份 PRD 摘要（≤ 2KB）。

---

## 6. 课后作业

1. 跑一遍 memory-curate Skill
2. 在自己项目里至少写 1 个 PRD_SUMMARY 实例
3. 在 LEGACY_FACTS 里记 1 条你今天工作中发现的"事实"
4. 完成 [06-Skill-Owner培训.md](06-Skill-Owner培训.md)

---

## 自检

- [ ] 我能区分 fact 和 inference
- [ ] 我会写 inference 的 derives_from + 置信度 + 过期条件
- [ ] 我知道周一跑 memory-curate
- [ ] 我会用 PRD_SUMMARY 模板写一份 ≤ 2KB 摘要
