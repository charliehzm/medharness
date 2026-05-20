# 研发交付 SOP v2.2 · 微 Change 快速通道（5 步精简版）

> 与主 SOP-v2 配套：**完整 12 步**适用于 feature / 多 stage；**本 5 步**适用于 micro-change（bugfix / docs / 小配置）。
> 维护：技术委员会 + 合规委员会
> 触发：v2.2 实战反馈（B4，micro-change 占 42% + 17% = 59% 全部走 12 步过重）

---

## 1. 适用范围（强约束）

micro-change **必须同时满足**以下条件：

- [ ] 改动 ≤ 2 个文件
- [ ] 不触动 fields.yml 中任何 L3/L4 字段处理路径
- [ ] 不新增/修改 API 接口契约
- [ ] 不引入新的 LLM 调用
- [ ] 不修改 spec / design / TDD（仅修代码 / 文档 / 配置）
- [ ] 不修改 `.audit/` `governance/runbooks/` `.claude/` 下的内容

**任一不满足 → 必须走完整 12 步 SOP**。

不满足判定由 `scripts/sop_router.py`（详见下）自动执行。

## 2. 五步流程

### Step μ1 · 微合规预检（≤ 5 分钟）

- 调 Skill: `$compliance-precheck-micro`（v2.2 新增 alias 模式）
- 输入：变更描述（一句话）+ 改动文件路径列表
- 自动校验：
  - 文件数 ≤ 2 ✓
  - 改动路径不在 L3/L4 列表 ✓
  - 无新 LLM 调用（grep `mcp-model-router` 调用差异） ✓
- 产物：`MICRO_TAG.md`（极简版 COMPLIANCE_TAG）
- 退出准则：自动检查全过 + 自我声明"无 PHI 触动"

### Step μ2 · 实现（直接编码）

- 调 Skill: `$openspec-apply-change` 或 `$systematic-debugging`（如修 bug）
- 改 ≤ 2 文件
- 无需 PRD / TDD / OpenSpec change（micro 不入 OpenSpec）

### Step μ3 · 验证（单元 + 简易回归）

- 调 Skill: `$mocking-stubbing`（仅跑相关 test）
- 不需要 mock 数据生成（复用既有）
- 不需要 Compliance-Agent Step 10

### Step μ4 · 自检 Review（可选 AI Reviewer 或人工）

- 调 Skill: `$requesting-code-review`
- Reviewer 可以是同模型（micro 不强制异构，因为风险低）
- 不进 REVIEW_THREAD.md 长流程；直接 PR comment

### Step μ5 · 轻量审计归档

- 调 Skill: `$audit-snapshot-micro`（v2.2 新增）
- 产物：`MICRO_AUDIT.json`（轻量审计包，仅 diff + MICRO_TAG + test 结果）
- 写入 `mcp-audit-log`（event_type: `micro_change_seal`）
- **不**生成完整 AUDIT_BUNDLE.tar.gz

---

## 3. 关键产物对照

| 产物 | 12 步 SOP | 5 步 micro |
|---|---|---|
| COMPLIANCE_TAG | ✅ 必备 | MICRO_TAG（简化版） |
| MODEL_ALLOWLIST | ✅ 必备 | 继承父分支或母 change |
| PRD / TDD | ✅ 必备 | ❌ 不写 |
| OpenSpec proposal/design/specs/tasks | ✅ 必备 | ❌ 不入 OpenSpec |
| VERIFY_REPORT | ✅ 必备 | 自动从 test 输出 |
| REVIEW_THREAD | ✅ 必备 | PR comment 即可 |
| TEST_REPORT | ✅ 必备 | 简化为 test 输出 |
| COMPLIANCE_REPORT | ✅ 必备 | ❌ 不跑 Step 10 |
| AUDIT_BUNDLE.tar.gz | ✅ 必备 | MICRO_AUDIT.json（轻量） |

## 4. MICRO_TAG.md 模板

```markdown
# MICRO_TAG — <change-name>
- 触发条件: bugfix / docs / 配置
- 文件清单: 
  - path/to/file1
  - path/to/file2
- 不触动 L3/L4 字段路径: ✓ (自动校验通过)
- 无新 LLM 调用: ✓ (自动校验通过)
- 父分支 MODEL_ALLOWLIST 继承自: openspec/changes/<parent-change>
- 自我声明 (开发者签字): "本变更无 PHI 触动" — <name> <date>
```

## 5. MICRO_AUDIT.json 模板

```json
{
  "schema_version": "1.0",
  "type": "micro_change",
  "change_name": "...",
  "files_changed": ["path/to/file1", "path/to/file2"],
  "diff_sha256": "sha256:...",
  "test_result": "PASS",
  "test_summary": {"unit": 5, "passed": 5},
  "developer": "...",
  "archived_at": "ISO-8601",
  "parent_change": "openspec/changes/...",
  "mcp_audit_log_receipt": {"row_id": "...", "self_hash": "sha256:..."}
}
```

## 6. 何时强制升级到 12 步 SOP

如下情况，即便初判为 micro，也必须升级：

- Hook `phi_detect_v3` 在任何 prompt 触发阻断 → 升级
- `sop_router.py` 检测到 fields.yml 中 L3/L4 字段被读写 → 升级
- 改动文件 > 2 → 升级
- 任何 LLM / 外部 API 调用 → 升级
- 多次 micro 累计触及核心模块（5 次内对同一模块）→ 升级（防止"micro 累计绕过 SOP"）

## 7. 月度 / 季度治理

- Compliance Officer 每月抽 10% micro-change 做"事后扫描"
  - 检查是否真的没触 PHI / L3/L4
  - 检查 MICRO_AUDIT 完整性
  - 任何遗漏 → micro 通道整改 + 涉事开发者培训
- 季度评估：micro 占比、micro 升级到完整 SOP 的比率、micro 触发审计事件率
- micro 比率应 ≥ 40%（M2 实测的 59% 上限）；不达标 → 审视 sop_router 阈值

## 8. 不允许的"伪 micro"

- 把大 change 拆成 10 个 micro-change 绕开 12 步：sop_router 检测同模块连续 micro 累计 → 升级
- 在 micro 内偷偷碰 L3/L4：抽查 + 红队样本
- micro 用于跨模块 refactor：必须走完整 SOP

## 9. 与 12 步 SOP 的关系

```
新需求 → sop_router 判定
   ├─ micro (符合条件) → 走 5 步 (本文档)
   └─ feature/大 change → 走 12 步 (SOP-v2.md)
```

micro 不是"简化版"，是**完全独立的并行通道**，覆盖体系 SOP 之外的低风险场景。
