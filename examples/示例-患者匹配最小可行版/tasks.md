# Tasks · 患者匹配最小可行版

> Step 4 拆解输出。每项 ≤ 2 文件、单文档可独立完成、命名中文。

---

## 任务清单

### T1 · 数据合规预检（Step 0 产物 review）
- 文件：`.compliance/COMPLIANCE_TAG.md`
- 检查：4 字段（姓名 / 身份证 / 手机 / 病案号）的分级都 = L4
- 模型 allowlist：仅 Qwen 32B 本地 / DeepSeek V4-Pro 私有
- 输出 owner 签字

### T2 · fields.yml 中医院 MRN 模式扩展
- 文件：`fields.yml`
- 加入 `cn_mrn` recognizer：本院规则 `^[A-Z]{2}\d{8}$`
- 单测：`tests/integration/test_fields_cn_mrn.py`

### T3 · 合成测试数据集生成
- 文件：`tests/data/synthetic_patients_5k.csv`
- 用 `test-data-generation` Skill 合成 5000 条
- 指纹核验：与真实 PHI 反演风险 = 0
- README 注明：100% 合成、`Faker zh_CN` + 自定义 MRN 生成器

### T4 · 匹配引擎核心
- 文件：`src/matcher.py`
- 输入：dict[字段→值]
- 内部：先经 `mcp-desensitize` → 决策 → 反向映射
- 输出：(match_id, confidence, audit_handle)

### T5 · MCP 调用封装
- 文件：`src/clients.py`
- 三个 client：`phi_desensitize_client` / `model_router_client` / `audit_log_client`
- 每次 LLM 调用必经 model-router

### T6 · 单测 + 集成测试
- 文件：`tests/integration/test_matcher.py`
- 验证 5000 条合成数据匹配
- 错配率 < 0.5%
- 单条 < 200ms

### T7 · Verify Hook 跑通
- 跑：`openspec-verify-change` Skill
- 输出：Verify 报告（一次过率应 ≥ 75%）

### T8 · 合规 Gate（Compliance-Agent 异构模型）
- 检查项见 SOP Step 10
- 输出：`COMPLIANCE_REPORT.md`
- 高风险 0、中风险有 owner 签字

### T9 · 审计冻结
- 跑：`audit-snapshot` Skill
- 输出：`AUDIT_BUNDLE_患者匹配最小可行版_<ts>.tar.gz`
- 哈希上链 `mcp-audit-log`

---

## 任务依赖图

```
T1 ──→ T2 ──→ T3 ──→ T4 ──→ T5 ──→ T6 ──→ T7 ──→ T8 ──→ T9
```

每个任务独立 commit；每个任务 owner 签字后才能进下一个。
