# COMPLIANCE_TAG · feat-edge-tier-production-v0.5.0

> Step 0 合规预检产物。**任何代码动手前必须三方签字**。
> 本 change 跨越 L5 合规层多模块，合规风险**高**。

---

## 1. 数据字段分级

| 字段类别 | 内容 | 分级 | 处理 |
|---|---|---|---|
| 合成测试数据 | Faker zh_CN 生成的姓名 / 身份证 / 手机 / MRN | **L1**（合成 · 公开） | 可入 prompt / 可日志 / 可打包到 release |
| Presidio recognizer 规则 | 31 fields.yml | L1 | 同上 |
| 客户配置占位 | `.memory/项目档案.local.md` 模板状态 | L1 | 同上 |
| 客户化后真实配置 | `.memory/项目档案.local.md` 填充后 | L2-L4（视客户而定） | **不进 git** · 不打入 release · 客户自留 |
| PHI 演练 fixtures | `tests/red-team-drills/fixtures/synthetic_phi_corpus.jsonl` | **L1**（合成） | 可入 git · 可打包 |
| **真实 PHI** | 任何客户真实患者数据 | **L4** | **永不进 git · 永不打包 · 永不入 prompt** |

⚠️ **强约束**：本 change 内**不允许任何 commit 含真实 PHI**。
所有测试数据必须经 `test-data-generation` Skill 生成 + 指纹核验通过。

## 2. 模型 allowlist

本 change 实现期间允许使用的模型：

| 用途 | 模型 | 厂商家族 | 数据驻留 |
|---|---|---|---|
| 编码主力（codex） | GPT-5 / o1-codex / OpenAI 系 | openai | 公共 API（不接触 L3+ 数据） |
| Code Review（Reviewer-Agent · 异构） | Claude Opus 4.7 / Claude Sonnet 4.6 | anthropic | 公共 API |
| 合规审查（Compliance-Agent · 异构） | DeepSeek V4-Pro / Qwen 32B | deepseek / alibaba | 公共 API 或私有 |
| 架构决策 | Claude Opus 4.7 | anthropic | 公共 API（仅零 PHI 抽象设计） |
| 测试数据生成 | 任意（仅消费 L1 合成） | 任意 | 任意 |

### 异构性强制（runtime check）

- Coder 模型与 Compliance-Agent 模型 **必须不同厂商家族**：
  - openai vs anthropic ✅
  - openai vs deepseek ✅
  - openai vs alibaba ✅
  - openai vs openai ❌（同家族）
  - claude opus vs claude sonnet ❌（同家族）

实施这一约束的代码本身就在 `mcp-model-router` 内，本 change 要把它从 demo 改成 runtime gate。

## 3. 测试数据合规

- 所有 fixtures 必须由 `test-data-generation` Skill 产出
- 必经指纹核验（不能反演到真实生产数据）
- 来源声明：100% 合成 · 无任何生产采样
- 红队 drills 用的 fixtures `synthetic_phi_corpus.jsonl` 当前已含合成示例

## 4. 审计要求

- 本 change 跨 20 子任务 → 每个子任务**独立 commit + PR**
- 每个 PR 必含 AUDIT_BUNDLE 摘要（micro 通道 simplified 也行）
- 最终 v0.5.0-edge 发布时打 1 个整体 AUDIT_BUNDLE
- 保留期：≥ 6 年（HIPAA 标准）
- 存储：开发期 ClickHouse 本地；release 时归档到 `~/medharness-private/audit/v0.5.0/`

## 5. PHI 漏出预案

如本 change 实施中发现：
- 任何 commit 含真实 PHI → **立即 force-push 重写 history**（与 sanitize 同流程）
- Hook 漏报（false negative） → 标 🔴 P0 + 写 incident report 到 `HANDOFF/inbox/`
- 模型路由被绕 → 同上

## 6. 签字（**未签字 = 不能进 Phase 1**）

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 提案人 | charliehzm | 2026-05-21 | ✅ |
| Compliance Officer | charliehzm（兼任） | ____ | ☐ |
| 技术 Lead | charliehzm | ____ | ☐ |

⚠️ Compliance Officer 兼任风险：MVP 期可接受（v2.2 沿用）。M4 后强制拆岗。

## 7. 验签命令（任意人可跑）

```bash
# 任一 PR / commit 前
git log openspec/changes/feat-edge-tier-production-v0.5.0/ --grep="real PHI\|production data\|customer name" 
# 期望：空输出

# 任一 fixtures 文件
python tools/phi_fingerprint_check.py tests/red-team-drills/fixtures/*.jsonl
# 期望：所有文件 fingerprint == synthetic
```

（`tools/phi_fingerprint_check.py` 待 T1 同步实现）
