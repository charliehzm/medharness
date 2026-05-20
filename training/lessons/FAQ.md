# 培训 FAQ · 学员最常问的 20 个问题

> 持续更新。新问题在 [Discussions #1 FAQ](https://github.com/charliehzm/medharness/discussions/1) 提，我们筛进这里。

---

## 一、入门

### Q1 我是 PM / Compliance / 法务，不写代码，要学吗？
A: 课件 01（体系总览）+ 04（合规 Hook）+ 06（如果你是 Skill Owner）必学。
其他选修。

### Q2 我之前没用过 Claude Code，能学吗？
A: 可以。SKILL.md 是文本，原理上任何 LLM 都能读。先学 SOP / Skill 矩阵的概念，工具迁移容易。

### Q3 培训需要多久？
A: 自学 8-15 小时（7 个课件 + 实操）。配合 90 天督导 1-on-1。

### Q4 如果我不跟课件顺序学？
A: 01 必先（体系总览）。02-05 任意。06 / 07 留到 Day 30+。

---

## 二、SOP

### Q5 我的改动很小，必须走 12 步吗？
A: 不必。看 [02-12步SOP手把手 §3](02-12步SOP手把手.md)。≤ 2 文件 + 不触 PHI / 模型 / 审计 → 走 5 步 micro。

### Q6 Step 0 三方签字太重了，能省吗？
A: 不能。但 micro 通道 1 方签字 OK（你自己当提案人 + tech lead）。
**永远不能没有签字**——这是合规边界。

### Q7 Step 10 合规 Gate 拦了我，我能 override 吗？
A: 高风险 = 0 容忍，不能 override。
中风险 = owner 签字可放行。
低风险 = warn，可继续。
紧急 override → 双委员会签字。

### Q8 我跑 dryrun 卡了，怎么办？
A: 看 [docs/troubleshooting.md](../../docs/troubleshooting.md) Top 10。
还卡 → 开 Issue 用 `bug_report` 模板。

---

## 三、Skill / Hook

### Q9 23 个 Skill 记不住？
A: 不用记。看 [Skill 矩阵速查](03-Skill矩阵速查.md) 当字典查。
反复用的就 4-5 个核心（compliance-precheck / phi-desensitize / openspec-apply / openspec-verify / audit-snapshot）。

### Q10 Hook 误判把我阻断了，怎么办？
A: 三步：
1. 看 [04-合规Hook与PHI防护 §4](04-合规Hook与PHI防护.md) 复盘流程
2. 在 [Discussions #4](https://github.com/charliehzm/medharness/discussions/4) 提
3. 短期：用 v3 已知 suppress 规则 / 改 prompt 写法绕开（**不要**关 Hook）

### Q11 phi-detector 在哪？我能改它吗？
A: `mcp/phi-detector/server_v3.py`。
- 你可以提 PR 加规则
- 不能改默认 recall < 92%
- 改完跑 `bash tests/red-team-drills/run_all.sh`

---

## 四、合规

### Q12 PHI 是什么？哪些字段算？
A: HIPAA 18 标识符 + 中国 PIPL 额外字段。
看 `fields.yml`（31 字段）。简单记：能识别个体的医疗 / 个人信息都算。

### Q13 我处理境外用户数据，合规规则一样吗？
A: 不一样。HIPAA / GDPR / PIPL 边界不同。看自己公司的 COMPLIANCE_TAG.md 是按哪个框架配的。

### Q14 我的客户要审计，怎么办？
A: 4 小时内交付：
```bash
# 找出该 change 的 AUDIT_BUNDLE
ls AUDIT_BUNDLE_<change-name>_*.tar.gz
shasum -a 256 *.tar.gz  # 给客户哈希校验
# 客户用 mcp-audit-log 回放
```

### Q15 v2.0→v2.2 演化教训能分享吗？
A: 可以。看博客 [《NPS 18→40+：v2.2 八大改进》](https://medharness.dev/blog/m5-nps-v22)（M5 发）。

---

## 五、Memory

### Q16 我每天写 Memory 太累
A: 你不该每天写。Memory artifact 是**摘要**，不是日记：
- PRD_SUMMARY · 每个 change 1 份
- LEGACY_FACTS / INFERENCES · 发现新事实 / 推断时记
- ARCH_INPUT_INDEX · 每个 change 实现前 1 份

### Q17 fact 和 inference 我老分不清
A: 简单判断：
- "数据库字段是 VARCHAR(200)" → fact（grep 可证）
- "为什么是 200" → inference（猜的，必含 derives_from）

### Q18 Memory artifact 怎么 sync 到团队？
A: 都是 git 文件，commit + push 即同步。
不要把 memory 当聊天工具——它是**项目档案**。

---

## 六、社区 / 商业

### Q19 我们公司能用商业版吗？
A: M6（约 5-6 个月后）开放。需求强 → 联系 sales@medharness.io 入早期客户。

### Q20 我提了 issue 没人回？
A: 我们承诺 24h 内首次回复。
未回 → @ maintainer / 在 Discussions 重 ping。
普通 issue 14 天内解决或闭。

### Q21（补充）我想 own 一个 Skill
A: 看 [06-Skill-Owner培训](06-Skill-Owner培训.md)。
门槛：5 个相关 PR merged + Discussions 申请。

---

## 七、错误模式

### Q22 我能关 Hook 加速吗？
A: **不能**。这是 R5 红线。
真要关 → 双委员会签字 → 紧急情况限时（24h 内）。
为了 speed 关 hook → 6 个月后审计找不到东西 → 客户翻车。

### Q23 我能复制几条生产数据当测试用吗？
A: **不能**。R4 红线。
用 `test-data-generation` Skill 合成 + 指纹核验。

### Q24 我能用 Claude Opus 当合规 Agent 吗（如果 Coder 也是 Claude）？
A: **不能**。R2 + 异构性强制。
Coder 用 Claude → Compliance-Agent 必须 DeepSeek / Qwen / GPT 等不同厂商家族。

---

## 八、提交 / 没看到我的问题？

回 [Discussions #1 FAQ](https://github.com/charliehzm/medharness/discussions/1) 帖子提，我们 24h 内回 + 筛进本文。
