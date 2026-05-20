# 合规自检 checklist（PR 必填的 5 问详解）

> [.github/pull_request_template.md](../.github/pull_request_template.md) 里有 5 个合规自检问题。
> 这份文档展开"怎么答 / 案例 / 反例"。

---

## Q1 本 PR 是否会让 PHI 进入 prompt 路径？

### 否（多数 PR）
- 改文档 / 测试 / CI 配置 / 重构（不动数据流）
- → 勾"否"，下一题

### 是
- 改了任何与 LLM 调用相关的代码
- 改了 mcp/phi-detector / mcp/desensitize
- 引入新的 RAG / search 调用

**勾"是"前必做**：
1. 确认 PHI 入参前经过 `phi-desensitize` Skill
2. 反向映射表存 KMS（不在内存 / 不在日志）
3. 在 PR 描述贴一段："PHI 流入 → desensitize 输出 → LLM 输入" 的数据流图

### 反例（曾经踩过的）
```python
# ❌ 直接把患者姓名传给 LLM
result = llm.generate(f"Summarize visits for {patient.name}")

# ✅ 先脱敏
masked_name = phi_desensitize(patient.name)
result = llm.generate(f"Summarize visits for {masked_name}")
# 用完反向映射表（仅受控环境）
```

---

## Q2 本 PR 是否新增 LLM 调用？

### 否
- 重构 / 优化已有调用（不增加新调用点）
- → 勾"否"

### 是
- 任何 `client.complete()` / `chat()` / `generate()` 新增点

**勾"是"前必做**：
1. 走 `mcp-model-router` 而非直连
2. 在 `COMPLIANCE_TAG.md` 的 model allowlist 内
3. 异构性检查（如属合规审查 Agent → 与 Coder 厂商不同）

### 反例
```python
# ❌ 直连境外公共 API
import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_KEY"))

# ✅ 经 router
from mcp.model_router import route
client = route(task="code-review", data_level="L2")
```

---

## Q3 本 PR 是否绕过任何 Hook？

### 否
- 不改 `.claude/settings.json`
- 不改 `scripts/hooks/*.py`

### 是（罕见）
- 紧急修 hook 误判 → 改 phi_detect_v3.py 规则
- 紧急关 hook → **需双委员会签字 Issue 编号**

**勾"是"前必做**：
1. 提一个 Issue 用 `compliance_concern` 模板
2. 取得双委员会签字
3. 在 PR 描述链接该 Issue 编号

### 反例
```diff
# ❌ 在 .claude/settings.json 里关 Hook
- "PreToolUse": ["scripts/hooks/phi_detect_v3.py"]
+ # "PreToolUse": []   # disabled for speed

# ✅ 关掉用 issue + 双签字
+ # disabled per #142, signed by tech-lead + compliance-officer 2026-05-15
```

---

## Q4 本 PR 是否处理真实生产数据？

### 否（绝大多数应该勾此）
- 用 `test-data-generation` Skill 合成
- 用 `tests/red-team-drills/fixtures/` 已有合成数据

### 是
- **几乎不应该勾"是"**
- 真有合理场景 → 必走 `phi-desensitize` 全脱敏 + 指纹核验

**勾"是"前必做**：
1. 数据来源声明（哪个客户 / 哪个表 / 取样规则）
2. 指纹核验通过（不能反演原始）
3. 双委员会签字 Issue

### 反例
```bash
# ❌ "我从生产 copy 几条脱敏一下"
psql prod -c "SELECT * FROM patients LIMIT 10" > test_data.csv
sed -i 's/张/X/g' test_data.csv  # ← 这不是脱敏，是骗自己

# ✅ 合成
python -m mcp.test_data_generation --schema patient --count 5000 \
  --output tests/data/synthetic_patients_5k.csv --fingerprint-check
```

---

## Q5 本 PR 是否影响审计血缘？

### 否
- 不改 mcp-audit-log / openspec/templates/AUDIT_BUNDLE.spec.md
- 不改 audit-snapshot Skill

### 是
- 改 AUDIT_BUNDLE schema
- 改 lineage_graph.json 字段
- 改哈希链算法

**勾"是"前必做**：
1. AUDIT_BUNDLE schema 是否 backward-compatible？
2. 老版本 bundle 能否被新版工具 replay？
3. 在 manifest 中 bump `schema_version`

### 反例
```python
# ❌ 改 schema 但不 bump version
manifest = {
    "change_name": ...,
    "new_field": ...,  # ← 新字段，老 replay 工具读不到 / 报错
}

# ✅ bump version + 工具支持 N-2 schemas
manifest = {
    "version": "1.1",  # was "1.0"
    "change_name": ...,
    "new_field": ...,
}
```

---

## 一个 PR 的全套自检流程

```
1. 看 5 问，逐一答（≤ 2 分钟）
2. 任一问"是" → 看上面"勾'是'前必做"
3. 全"否" → 走标准 review 流程
4. 任一"是" → @合规 owner review
```

---

## 我答不上 / 不确定怎么办

- 在 PR 描述里写 `@medharness-org/compliance review needed`
- 或在 Discussions #5 提问
- **不要瞎填**——错误填写本身是合规违规

---

## 一句话

> 5 问 2 分钟。不愿花这 2 分钟 → 你 6 个月后审计花 4 小时也找不到的代价。
