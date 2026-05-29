# Spec · B1 · 出站输出安全 `mcp/outbound-safety/`

> 后端 lane（Codex #1）· 实现前必读。leaf 拆解在阶段 A 完成。

---

## Purpose

新建出站安全闸门：扫**模型响应**，与入站闸门对称。检出三类风险并处置——PHI 回流（拦截）/ 有害内容（拦截）/ 幻觉医嘱（**仅告警**，v0.6 不阻断）。命中事件落 `mcp-audit-log`，聚合供 A0 `/traffic` 与 `/events` 端点。

## Inputs

- `response_text: str` · 模型返回的响应文本（最长 16384 chars）
- `context: {"upstream": str, "ctx": "dev|prod", "data_level": "L2|L3|L4", "request_ref": str}`
- `policy: {"phi_reflow": "block|desensitize", "harmful": "block", "hallucination": "warn"}`

## Outputs

```python
{
  "decision": "pass|desensitized|blocked|warned",
  "classifications": [
    {"type": "phi_reflow|harmful|hallucination", "score": float, "disposition": str}
  ],
  "sanitized_text": str | None,   # 命中 PHI 回流且 policy=desensitize 时返回占位符版本
  "event_ref": str,               # 落审计后的引用，如 out#a1b2
  "stats": {"duration_ms": float}
}
```

## Constraints

- C1 · **0 PHI 原文留存**：命中 PHI 回流 → 脱敏为占位符或阻断；日志 / 返回体 / A0 端点**只记分类与聚合**，绝不含响应原文或 PHI 原文（与入站 C1 同红线）
- C2 · 幻觉医嘱 v0.6 **只 warn 不 block**（判定不成熟，攒数据）
- C3 · 有害内容 / PHI 回流命中 → block（或 PHI 可 desensitize）
- C4 · p99 ≤ 50ms（整段响应，1K-4K chars）；流式 SSE 边扫边转发**留 v0.7**，本 task 按整段扫
- C5 · 仅对 `data_level ∈ {L3,L4}` 的上下文强扫；L2 可轻量扫以省延迟
- C6 · 内部若调用 LLM 做分类 → **必经 mcp-model-router**（R2），不得直连
- C7 · 事件必落 `mcp-audit-log`（R3），与入站对称
- C8 · PHI 回流检测**复用 `mcp/phi-detector/`**，不重造检测器

## Architecture

```
response_text
  → 分类器（规则优先 + 可选 LLM via model-router）
      ├─ PHI 回流  → phi-detector 扫 → 命中: desensitize/ block
      ├─ 有害内容  → block
      └─ 幻觉医嘱  → warn（不阻断）
  → 落 audit-log（分类 + 处置 + ref，无原文）
  → 暴露聚合给 A0 /traffic.outbound 与 /events(cat=sec,type=输出)
```

## Test / DoD

- 出站合成 corpus（经 test-data-generation + 指纹核验）覆盖 4 类：PHI 回流 / 有害 / 幻觉 / 正常（负样本）
- red-team drill：PHI 回流拦截率 ≥ 0.95；p99 ≤ 50ms
- 校验：日志 / 返回体 / A0 端点 **0 PHI 原文**（接入 api-phi-exfil drill）
- 事件正确落审计且可被 `/events` 聚合
