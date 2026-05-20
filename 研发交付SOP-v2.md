# 研发交付 SOP v2（医疗数据 SaaS · 12 步 Spec-driven 流程）

> 本版本在原 9 步 [研发交付SOP(1).md](研发交付SOP(1).md) 基础上扩展为 **12 步**，新增 Step 0 / Step 10 / Step 12 合规层。
> 现有 9 步语义全部保留，**编号在 v2 中重新排布**（详见第 4.2 节）。
> 适用：医疗数据 SaaS / 数据中台 change 的全生命周期。
> 维护：技术委员会 + 合规委员会共同维护，任一委员会可发起修订。

---

## 1. 适用范围

- 基于 PRD/TDD 的分阶段研发交付。
- 主流程覆盖：合规预检 → PRD 预检 → TDD 对齐 → OpenSpec 文档化 → 任务拆解 → Mock 数据 → 实现 → Verify → Code Review → Mocking 测试 → 合规 Gate → 审计冻结归档。
- 合规约束：HIPAA + PIPL + 数据安全法 + 健康医疗数据安全指南。

---

## 2. 全局约束（继承 v1）

- **阶段串行**：阶段 N 归档完成后，才允许进入阶段 N+1。
- **阶段内按优先级串行**：不并行跳任务。
- **步骤门禁**：每一步开始前必须检查前序步骤完成。
- **Skill 显式调用**：每一步执行前先声明本步要用的 skill 名称（示例：`$compliance-precheck`、`$openspec-apply-change`）。
- **前后端任务分开**维护。
- **每个任务最多改动 2 个文件**。
- **每个任务必须有独立任务文档**。
- **文档和目录命名尽可能使用中文**。

## 2.1 全局约束（v2 新增 · 合规相关）

- **PHI 不可入 prompt**：所有含 L4 字段的文本必须先经 `phi-desensitize` 处理。
- **模型按 allowlist 路由**：所有模型调用走 `mcp-model-router`，越权调用被 Hook 阻断。
- **审计全量记录**：每个 tool call / Skill call / model call 必须落 `mcp-audit-log`。
- **测试数据合规**：禁用真实 PHI 反演，强制走 `test-data-generation` 合成 + 指纹核验。

---

## 3. Skill 映射总表（v2 · 按步骤）

| 步骤 | 必用 Skill | 可选 | 合规 Gate |
|---|---|---|---|
| 0 合规预检 | `compliance-precheck` | — | ✅ |
| 1 PRD 预检与补全 | `prd-implementation-precheck`、`prd` | `ask-questions-if-underspecified` | — |
| 2 TDD 对齐 | `prd-implementation-precheck` | `ask-questions-if-underspecified` | — |
| 3 OpenSpec 产物生成 | `openspec-new-change` → `openspec-continue-change` | `openspec-ff-change` | — |
| 4 任务拆解 | `task-decomposition` | — | — |
| 5 Mock 数据生成 | `test-data-generation` | `phi-desensitize`（如涉及真实数据脱敏） | ✅ |
| 6 OpenSpec Apply | `openspec-apply-change` | — | — |
| 7 Verify + 修复未实现工件 | `openspec-verify-change` | — | ✅ |
| 8 Code Review + Debug 闭环 | `requesting-code-review`、`systematic-debugging` | — | — |
| 9 Mocking 测试与调试闭环 | `mocking-stubbing`、`systematic-debugging` | — | — |
| 10 合规审查 Gate | `compliance-review` | `phi-desensitize` | ✅ |
| 11 最终复修（如有合规整改） | `systematic-debugging` | `openspec-apply-change` | — |
| 12 归档 + 审计冻结 | `openspec-archive-change`、`audit-snapshot` | `openspec-sync-specs`、`memory-curate` | ✅ |

---

## 4. 前序步骤完成检查（每步必做）

- 进入步骤 0 前：业务需求草稿可读、字段清单初版可见。
- 进入步骤 1 前：步骤 0 已完成，`COMPLIANCE_TAG.md` 已签字，`MODEL_ALLOWLIST.json` 已注入 router。
- 进入步骤 2 前：步骤 1 已完成，PRD 无 blocker / warning，且已分阶段。
- 进入步骤 3 前：步骤 2 已完成，用户已提交新的 TDD，且 TDD 已对齐最终 PRD。
- 进入步骤 4 前：步骤 3 已完成，当前阶段 `proposal/design/specs/tasks` 已齐全。
- 进入步骤 5 前：步骤 4 已完成，任务已拆解且满足"前后端分离、每任务最多 2 文件、单任务单文档、按优先级排序"。
- 进入步骤 6 前：步骤 5 已完成，每阶段 mock 数据目录和数据已生成，且通过指纹核验（合成数据 vs 真实样本指纹库无重合）。
- 进入步骤 7 前：步骤 6 已完成，当前阶段任务已按优先级实现并勾选。
- 进入步骤 8 前：步骤 7 已完成，Verify 通过且未实现工件已修复。
- 进入步骤 9 前：步骤 8 已完成，code review + debug 闭环达到无 bug。
- 进入步骤 10 前：步骤 9 已完成，基于阶段 mock 的测试全部通过。
- 进入步骤 11 前：步骤 10 已完成，`COMPLIANCE_REPORT.md` 已签字，高风险 = 0。
- 进入步骤 12 前：步骤 11 已完成（如无合规整改可跳过），所有合规反馈已闭环。

门禁规则：
- 任一前序检查不通过，禁止进入下一步。
- 未通过时回退到对应步骤补齐，补齐后重新检查。
- **合规 Gate（0/5/7/10/12）失败必须升级**至 Compliance Officer，不允许开发者自行豁免。

---

## 5. 标准流程

### 步骤 0 · 合规预检（v2 新增）

开始前检查：
- 已提供业务需求草稿与初版字段清单。
- 已声明本步 skill：`compliance-precheck`。

1. PM-Agent 对业务需求与字段清单做数据分级（L1-L4）。
2. 起草 `openspec/templates/COMPLIANCE_TAG.md` 实例并填写字段清单（最小化原则）。
3. 生成 `MODEL_ALLOWLIST.json`，注入 `mcp-model-router`。
4. Compliance Officer（M1-M3 兼任：QA Lead + 法务联签）签字。

输出：
- 签字的 `COMPLIANCE_TAG.md`。
- 生效的 `MODEL_ALLOWLIST.json`。

退出准则：
- 数据分级签字、字段最小化、allowlist 生效、所有"是"风险有缓解措施。

---

### 步骤 1 · PRD 预检与补全（继承 v1）

（语义同 v1 步骤 1，略；唯一变化：PRD 中必须引用 `COMPLIANCE_TAG.md` 的 change_id 与数据等级。）

---

### 步骤 2 · TDD 对齐（继承 v1 步骤 2）

（语义同 v1。）

---

### 步骤 3 · OpenSpec 产物生成（继承 v1 步骤 3）

新增要求：`design.md` 中必须包含一节《合规设计说明》，至少回答：
- 本设计中哪些字段属于 L3/L4？
- PHI 在系统内的流向（数据流图）。
- 是否引入新的境外/公共模型调用？

---

### 步骤 4 · 任务拆解（继承 v1 步骤 4）

提示词不变：
> 将所有任务进行拆分，其中前端与后端任务要分开，每个任务不超过 2 个文件的改动，每个任务单独任务文档，任务按照优先级排序，任务文档名称和文件夹名称尽可能用中文。

---

### 步骤 5 · Mock 数据生成（继承 v1 步骤 5 · 合规增强）

新增要求：
- 强制使用 `test-data-generation` 合成器，禁用 "sample-from-production"。
- 生成后跑指纹核验：`scripts/verify_test_data_fingerprints.py`，命中真实样本指纹库即失败。

---

### 步骤 6 · OpenSpec Apply（继承 v1 步骤 6）

（语义同 v1。）

---

### 步骤 7 · Verify + 修复未实现工件（继承 v1 步骤 7 前段）

（语义同 v1 步骤 7 前段。Verify 失败必须回到步骤 6 补齐。）

---

### 步骤 8 · Code Review + Debug 闭环（继承 v1 步骤 7 后段）

（语义同 v1 步骤 7 后段：`requesting-code-review` → `systematic-debugging` 循环至无 bug。）

新增：Reviewer-Agent 默认启用 `prompt-injection-scan`（在 RAG 检索结果上扫一遍）。

---

### 步骤 9 · Mocking 测试与调试闭环（继承 v1 步骤 8）

（语义同 v1。）

---

### 步骤 10 · 合规审查 Gate（v2 新增）

开始前检查：
- 步骤 9 已完成，所有 mock 测试通过。
- 已声明本步 skill：`compliance-review`（由 Compliance-Agent 独立执行，模型异构于主线）。

1. 自动生成本 change 的数据流图（基于 `LINEAGE_GRAPH.schema.json`）。
2. Compliance-Agent 对 diff + 数据流图 + 测试数据 执行合规扫描，检查：
   - PHI 是否在日志/异常/缓存中泄漏？
   - Prompt 注入面是否新增？
   - 模型调用是否符合 Step 0 allowlist？
   - 测试数据指纹是否合规？
3. 生成 `COMPLIANCE_REPORT.md`，等级：高风险 / 中风险 / 低风险。
4. Compliance Officer 签字（高风险 = 0 时方可签）。

输出：
- 签字的 `COMPLIANCE_REPORT.md`。

退出准则：
- 高风险 = 0；中风险已分配 owner 且有缓解计划。

---

### 步骤 11 · 最终复修（v2 新增 · 条件触发）

仅在 Step 10 有合规整改项时执行：

1. 使用 `systematic-debugging` 定位根因。
2. 用 `openspec-apply-change` 修复。
3. 回到步骤 10 复审。

退出准则：合规反馈全部闭环。

---

### 步骤 12 · 归档 + 审计冻结（合并并增强 v1 步骤 9）

开始前检查：
- 步骤 10/11 已完成。
- 已声明本步 skill：`openspec-archive-change`、`audit-snapshot`，可选 `memory-curate`。

1. 用 `openspec-archive-change` 归档当前阶段 change。
2. 用 `audit-snapshot` 按 [AUDIT_BUNDLE.spec.md](openspec/templates/AUDIT_BUNDLE.spec.md) 规范打包：
   - prompts / changes / compliance / test_data / lineage / verification / models / signatures
3. 计算哈希链，`ROOT_SHA256` 写入 `mcp-audit-log`（WORM）。
4. 可选执行 `memory-curate`：把本 change 的可复用经验沉淀进 `.memory/`。

输出：
- 归档完成的 change（v1 标准）。
- `AUDIT_BUNDLE_<change-id>_<archived_at>.tar.gz`（v2 新增）。
- `mcp-audit-log` 写入记录。

---

## 6. 阶段完成定义（DoD v2）

满足以下全部条件才可归档：

- 步骤 0：`COMPLIANCE_TAG.md` 签字、allowlist 生效。
- 步骤 1：最终 PRD 已定稿且无 blocker/warning。
- 步骤 2：对齐最终 PRD 的最终 TDD 已提交并通过对齐检查。
- 步骤 3：OpenSpec 产物完整（proposal/design/specs/tasks），含《合规设计说明》。
- 步骤 4：任务拆解满足"前后端分离 + 单任务单文档 + 单任务最多 2 文件"。
- 步骤 5：Mock 数据通过指纹核验。
- 步骤 6：任务实现已完成并勾选。
- 步骤 7：Verify 通过，未实现项已补齐。
- 步骤 8：code review + debug 闭环，无 bug。
- 步骤 9：基于 mock 的测试全部通过。
- 步骤 10：`COMPLIANCE_REPORT.md` 签字，高风险 = 0。
- 步骤 11：如有合规整改，全部闭环。
- 步骤 12：`AUDIT_BUNDLE` 打包、哈希链上链、可重放性自检通过。

---

## 7. 推荐执行节奏

1. **阶段规划**：步骤 0~5（合规预检 + 需求/设计/数据）。
2. **阶段实现**：步骤 6~9（实现 + Verify + Review + Mocking 测试）。
3. **合规闸门**：步骤 10~11。
4. **阶段收尾**：步骤 12（归档 + 审计冻结）。
5. 进入下一阶段并重复。

---

## 8. 与 v1 的差异对照表

| v2 编号 | v2 名称 | v1 编号 | 说明 |
|---|---|---|---|
| 0 | 合规预检 | — | **v2 新增** |
| 1 | PRD 预检与补全 | 1 | 继承（要求引用 COMPLIANCE_TAG） |
| 2 | TDD 对齐 | 2 | 继承 |
| 3 | OpenSpec 产物生成 | 3 | 继承（design 加合规说明） |
| 4 | 任务拆解 | 4 | 继承 |
| 5 | Mock 数据生成 | 5 | 继承（加指纹核验） |
| 6 | OpenSpec Apply | 6 | 继承 |
| 7 | Verify | 7 前段 | 继承 |
| 8 | Code Review + Debug | 7 后段 | 继承（加注入扫描） |
| 9 | Mocking 测试 | 8 | 继承 |
| 10 | 合规审查 Gate | — | **v2 新增** |
| 11 | 最终复修（条件） | — | **v2 新增** |
| 12 | 归档 + 审计冻结 | 9 | 增强（加 AUDIT_BUNDLE） |

---

## 9. Stage 配套脚本（继承 v1 Stage 3 章节，结构不变）

参见 v1 文档 `## Stage 3 补充：Fixture Runner 与灰度开关`。v2 体系下，所有 Stage 命令在 CI 中**多加一个 `audit-snapshot` 步骤**，确保灰度发布、回滚均有审计快照。

---

## 10. 变更历史

| 版本 | 日期 | 修改人 | 内容 |
|---|---|---|---|
| v1.0 | 2026-02-25 | 原作者 | 9 步 Spec-driven SOP |
| v2.0 | 2026-05-16 | AI Coding 体系建设项目组 | 扩展为 12 步，新增 Step 0/10/11/12 合规层 |
