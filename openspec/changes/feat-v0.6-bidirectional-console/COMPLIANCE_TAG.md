# COMPLIANCE_TAG · feat-v0.6-bidirectional-console

> Step 0 合规预检产物。**任何代码动手前必须三方签字**。
> 本 change 同时触及**出站 PHI 处理**与**面向人的可视化界面**，合规风险**高**。

---

## 1. 数据字段分级

| 字段类别 | 内容 | 分级 | 处理 |
|---|---|---|---|
| 合成测试数据 | Faker zh_CN 生成的姓名 / 身份证 / 手机 / MRN | **L1**（合成 · 公开） | 可入 prompt / 可日志 / 可打包 |
| 出站响应合成 corpus | 模拟模型响应含 PHI 回流 / 有害内容 / 幻觉医嘱 | **L1**（合成） | 经 test-data-generation 生成 + 指纹核验 |
| 模型响应（运行时） | 真实生产模型响应，可能含 **PHI 回流** | **L3-L4** | **出站闸门即时脱敏 / 阻断 · 不留存原文 · 日志只记分类与聚合** |
| 只读 API 返回体 | 态势分 / 聚合数 / 占位符 / 哈希 / 事件分类 | **L1**（聚合后） | 可经 API 出仓；**schema 白名单强制 · 永不含原始 PHI** |
| 安全事件 payload | 注入指令 / 有害内容原文 | **L4 等价（敏感）** | **不回显 · 不入 API · 不入前端**；只记分类标签 + 处置 |
| 前端 state / localStorage | Console 运行时数据 | 必须 **L1** | 只存占位符 / 哈希 / 聚合；**禁止缓存任何 PHI** |
| 真实 PHI | 任何客户真实患者数据 | **L4** | **永不进 git · 永不打包 · 永不入 prompt · 永不入 Console** |

⚠️ **强约束**：
- 本 change 内**不允许任何 commit 含真实 PHI**，前端 fixtures / mock 数据同样必须合成。
- **出站方向同样 0 PHI**：扫描模型响应命中 PHI → 脱敏为占位符或阻断，绝不在日志 / API / 前端出现原文。
- **只读 API 是新的出仓边界**：任何端点返回体必须过 schema 白名单，新增「API PHI 渗透」red-team drill 强校验返回体 0 PHI。

## 2. 模型 allowlist

| 用途 | 模型 | 厂商家族 | 数据驻留 |
|---|---|---|---|
| 编码主力（codex · BE + FE 两 lane） | GPT-5 / o1-codex / OpenAI 系 | openai | 公共 API（不接触 L3+ 真实数据） |
| Code Review（Reviewer-Agent · 异构） | Claude Opus 4.7 / Sonnet | anthropic | 公共 API |
| 合规审查（Compliance-Agent · 异构） | DeepSeek V4-Pro / Qwen 32B | deepseek / alibaba | 公共 API 或私有 |
| 出站安全分类器（运行时 · 如用 LLM） | 私有 Qwen / 规则优先 | alibaba / 本地 | **必经 mcp-model-router** |
| 测试数据生成 | 任意（仅消费 L1 合成） | 任意 | 任意 |

### 异构性强制
- 两个 Codex lane（BE + FE）都是 **openai 系 Coder**。
- Reviewer-Agent + Compliance-Agent **必须非 openai**（anthropic / deepseek / qwen）。
- 出站安全模块若内部调用 LLM 做分类，该调用**必经 mcp-model-router**（R2），不得直连。

## 3. 测试数据合规

- 所有 fixtures（含前端 mock、出站 corpus）必须由 `test-data-generation` Skill 产出 + 指纹核验。
- 出站 corpus 需覆盖：PHI 回流 / 有害内容 / 幻觉医嘱 / 正常响应（负样本）。
- 前端 mock 数据只用占位符（`__NAME_a1__`）+ 哈希（`routing#a1b2`）+ 聚合数，**不得**用任何形似真实 PHI 的字符串。
- 来源声明：100% 合成 · 无任何生产采样。

## 4. 审计要求

- 本 change 跨 7 task group（A0 / B1-B3 / F1-F3）→ 每个 leaf sub-task 独立 commit + PR。
- 每个 PR 必含 AUDIT_BUNDLE 摘要（micro 通道亦可）。
- 出站闸门自身的拦截 / 告警事件**必须落 mcp-audit-log**（R3），与入站对称。
- 只读 API 的每次查询可不逐条落审计，但**导出 AUDIT_BUNDLE 的动作**必须落审计。
- 保留期 ≥ 6 年。

## 5. PHI 漏出预案

- 任何 commit 含真实 PHI → 立即 force-push 重写 history（与 sanitize 同流程）。
- 只读 API 返回体被发现含原始 PHI → 标 🔴 P0 + 下线该端点 + incident report 到 `HANDOFF/inbox/`。
- 前端被发现把 PHI 写进 localStorage / URL → 同上 P0。
- 出站闸门漏报 PHI 回流 → 标 🔴 P0 + 红队回归。

## 6. 签字（**未签字 = 不能动手**）

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 提案人 | charliehzm | 2026-05-29 | ✅ |
| Compliance Officer | charliehzm（兼任 · M4 拆岗） | 2026-05-29 | ✅ 经 maintainer 授权代签 |
| 技术 Lead | charliehzm | 2026-05-29 | ✅ 经 maintainer 授权代签 |
| Compliance-Agent（异构） | ⟪回填·模型名/会话标识⟫ | ⟪回填·日期⟫ | ⟪回填·复审结论；PASS=✅ 异构复审通过⟫ |

> ⏳ **本行为占位**：本 PR 是异构复审签字回填模板。待独立非-anthropic 会话（DeepSeek / Qwen）跑完 Step 10 复审后——**PASS** 则用其返回的签字串替换上表三个 `⟪回填⟫` 占位、删除本注脚、转 Ready 再合并；**FAIL** 则关闭本 PR，main 维持 ⚠️ WAIVED 并按其意见整改。**回填前禁止合并。** 此前 Claude 侧 Step 8/10 review 见 PR #101 描述；WAIVED 始末见 main 上 COMPLIANCE_TAG §6 历史。

## 7. 验签命令（任意人可跑）

```bash
# 任一 PR / commit 前：扫真实 PHI 关键词
git log openspec/changes/feat-v0.6-bidirectional-console/ --grep="real PHI\|production data\|customer name"
# 期望：空输出

# 前端 mock / 出站 corpus 指纹核验
python tools/phi_fingerprint_check.py web/**/fixtures/*.json mcp/outbound-safety/tests/fixtures/*.jsonl
# 期望：所有文件 fingerprint == synthetic

# 只读 API 返回体 0 PHI（新增 drill · 见 B/A spec）
bash tests/red-team-drills/run_all.sh --only api-phi-exfil
# 期望：0 条返回体命中 PHI
```
