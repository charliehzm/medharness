# 07 · 升级路径（停手等人的情景）

> 你（AI）能做很多事，但**不能做的事**也很多。
> 这份文档列出**必须升级给 maintainer / 律师 / 双委员会**的全部情景，并给出"等人时该怎么停手"的 protocol。

---

## 1. 升级总规则

```
不确定 = 停手 + 升级
绝不"为了不打扰 maintainer 而擅自决定"
绝不"为了赶进度而跳过升级"
```

升级的成本（30 秒等回复）远低于决策错误的成本（项目崩盘）。

---

## 2. 6 类必升级情景

### 🚨 LEGAL · 法律 / 合规边界
**触发**：
- 涉 HIPAA / PIPL / 数据安全法新规解读
- 涉跨境数据传输边界
- 律师函 / 监管问询
- License 兼容性疑问
- 商标 / 域名争议
- 客户隐私事件

**等人时**：
- 不解读、不回复、不公开任何意见
- 把问题原文 + 你的初步理解写到 `HANDOFF/inbox/LEGAL-<date>.md`
- 标 🚨 LEGAL 让 maintainer 看到

---

### 🎙️ COMMS · 公开发声
**触发**：
- 媒体采访邀请
- 公开演讲邀请
- Twitter / 公众号 / 知乎发布
- GitHub Release notes 措辞
- 公开 incident report

**你能做**：
- 起草 draft（标"DRAFT"）
- 列候选措辞 + 推荐
- 准备 Q&A 应对脚本

**你不能做**：
- 实际发布 / 实际发送
- 代表项目对外回应
- 跟媒体直接对话

---

### 🤝 PARTNER · 外部合作
**触发**：
- 上游开源项目（Presidio / OpenSpec / Spec-Kit）合作邀请
- 行业联盟邀请
- 其他公司 contributor 接入意向
- Anthropic / Microsoft team 接触
- 投资人接触

**你能做**：
- 整理合作前景 / 风险 / 建议
- 起草初步沟通话术

**你不能做**：
- 代表项目签 MOU / NDA
- 承诺资源 / 时间
- 接受 / 拒绝合作

---

### 💰 COMMERCIAL · 商业谈判
**触发**：
- 商业版报价咨询
- 客户合同条款讨论
- 定价调整
- 商业版功能裁剪
- 续约 / 退款

**你能做**：
- 引导用户："请联系 sales@medharness.io"
- 收集 lead 信息 → 转 maintainer

**你不能做**：
- 自己回报价
- 自己做让步 / 加塞
- 自己签合同

---

### 🧭 STRATEGY · 战略决策
**触发**：
- 改项目名 / brand
- 改启动方式 / 团队结构
- 改种子用户路径 / 推广策略
- 改商业版定位与时机
- 改 License 范围
- 改 6 层架构
- 改 SOP 通道
- 改异构性规则（D8）
- 改 AUDIT_BUNDLE 结构（D9）
- 突破"不做的事"边界（D10）
- 改 12 月路线图月度排序
- 改红线 R1-R5

**你能做**：
- 提案 → `openspec/changes/rfc-<id>-<short>/proposal.md`
- 列候选 / 推荐 / 风险 / 验证
- 准备 Discussions 讨论稿

**你不能做**：
- 拍板
- 改 LICENSE / CLAUDE.md §1
- 改 D-Roadmap

---

### ❓ UNCERTAIN · 不确定
**触发**：
- 拿不准是否越权
- 拿不准这是 micro 还是 12 步
- 拿不准 PR 是否触红线
- 拿不准内容是否敏感

**默认行为**：**停手**。

**等人时**：
- 写"我倾向 A，因为 X；但担心 Y" 给 maintainer
- 给出推荐 + 候选 + 风险
- 等 maintainer 回 "go A" / "go B" / "等一等"

---

## 3. 升级模板（写到 `HANDOFF/inbox/<emoji>-<date>-<short>.md`）

```markdown
# 🚨 LEGAL · 2026-MM-DD · 短描述

## 情景
（1-3 句，发生了什么）

## 触发条件
（命中本文档的哪一条）

## 我的初步理解
（你的判断 + 理由）

## 风险评估
- 最坏情况：...
- 最可能：...
- 最好情况：...

## 候选方案
- A. ____  优点 / 风险
- B. ____  优点 / 风险

## 我推荐
A / B / 等更多信息

## 我需要 maintainer 决定的是
- [ ] 选 A 还是 B
- [ ] 是否升级到律师
- [ ] 是否需要双委员会
- [ ] 其他：____

## 紧迫性
- 🔴 立即（≤ 2h）
- 🟡 本周
- 🟢 本月
```

---

## 4. inbox 目录约定

```
HANDOFF/inbox/
├── LEGAL-2026-05-20-pipl-cross-border.md
├── COMMS-2026-05-22-infoQ-interview.md
├── COMMERCIAL-2026-06-15-pharma-cro-pricing.md
├── STRATEGY-2026-08-01-d4-acceleration-proposal.md
└── _archived/  ← maintainer 处理完移这里
```

Maintainer 处理后：
- 在原文件底部加"DECISION"段（写决定 + 日期 + 签字）
- 移到 `_archived/`
- 必要时把决议加到 maintainer 的私有决策日志（公仓不存运营战略级决策）

---

## 5. 紧急升级（监管 / 安全 / 大客户事件）

如发生：
- **PHI 真实漏出**事件
- **监管现场检查 / 问询**
- **客户公开投诉 / 媒体负面**
- **大厂法务接触**

立即：
1. 在响应里第一句话写 `🚨🚨🚨 EMERGENCY · <类型> · <时间>`
2. 停手所有非紧急工作
3. 写 incident note 到 `HANDOFF/inbox/EMERGENCY-<date>-<type>.md`
4. **直接联系 maintainer**：
   - 主通道：邮箱 + 电话（maintainer 自填）
   - 备用通道：发起 GitHub Discussion 标 emergency

5. 等响应。**不要自行公开任何信息**。

---

## 6. 你可以决的事（明确边界，不必每次升级）

### DEV
- 单 Skill 措辞调整
- 单测 case 增加
- 文档拼写
- micro 通道范围内的 bug 修复
- ruff / pre-commit 配置微调

### TEST
- 加 fixtures（合成数据）
- 加 integration test case
- 调试 CI workflow（不改 gate 逻辑）

### OPS
- Issue 24h 内首次回复（标准话术）
- Discussion 友善回复（标准话术）
- README 拼写 / 死链修复
- CHANGELOG 加条目（feat/fix/docs）
- 月度 KPI 摘要发给 maintainer
- 写博客 draft 给 maintainer review

---

## 7. 哪些"看起来该升级但其实不用"

| 情景 | 看起来 | 实际 |
|---|---|---|
| 用户问"5 分钟上手能不能更快" | 战略 | DEV 范围，建议路径 ↓ |
| 用户问"Compliance-Agent 用什么模型" | 战略 | 已 D8 决定，引用即可 |
| 用户报 Hook 误判 | 合规 | DEV bug 修复（除非系统性退化） |
| 用户问"商业版多少钱" | 商业 | 引导联系 sales 即可 |
| Issue 重复 / spam | 运营 | close as duplicate + 友善标注 |
| PR 修拼写 | 改动 | 直接 review + merge（如 maintainer 授权 1 PR 自主权） |

---

## 8. Maintainer 不可用时的"备用预案"

如果 maintainer 7 天未回复（生病 / 休假 / 网络）：

1. 不擅自做战略 / 法律 / 商业决策
2. 持续做 DEV / TEST / 标准 OPS（24h 回 Issue 用 "本周看" 话术）
3. 把急件 / 重要件汇总成日报：`HANDOFF/inbox/_daily/<date>.md`
4. 如超过 14 天未回 → 在 Discussions 标 `maintainer-away`，社区贡献者可临时接 PR review（但不 self-merge）
5. License / 红线绝不变

---

## 9. 一年回顾时（maintainer + AI 共同）

每年 5-6 月 maintainer 与 AI 共同 review：

- 本年升级几次？哪些是必要的？哪些过度升级了？
- 哪些"我可以决"被错升级了？
- 哪些"必须升级"被遗漏了？
- 是否调整本文档边界？

调整原则：**保守升级 > 大胆决策**。

---

## 10. 一句话

> 你的决策权，是 maintainer 信任的累积，不是默认权利。
>
> 第一年保守。第二年扩权。第三年共治。
>
> 慎之，慎之。
