# mcp-internal-kb

> 内部医学术语 / 业务知识 / 既有决议的检索 MCP server。

## 职责
- 提供按主题 / 关键词 / 向量的检索
- 内容覆盖：医学术语对照（ICD-10 / SNOMED / 中医术语 / 院内自定义代码）、业务术语、历史决议、合规条款摘要、内部 Wiki
- 所有返回内容须脱敏（不含 L3/L4 字段值）
- 检索结果通过 `prompt-injection-scan` 后才返回给主线 Agent

## 数据来源
1. 公司内部 Wiki / Notion / 飞书知识库
2. 公开医学知识库（ICD-10、SNOMED-CT、UMLS 中可商用部分）
3. 内部决议（governance/ 目录）
4. AUDIT_BUNDLE 的可复用经验摘要（M-Curator 周期性导入）

## 接口

### `search`
```jsonc
// request
{
  "query": "...",
  "k": 5,
  "filter": {"category": "medical-term | business | governance | wiki"},
  "context": {"change_id": "...", "tier_hint": "L1|L2"}
}

// response
{
  "hits": [
    {"id": "kb-1234", "title": "...", "snippet": "...", "source": "...", "confidence": 0.92,
     "injection_scan": "passed | quarantined | warn"}
  ]
}
```

### `ingest`
- 由 Memory-Curator 周扫触发
- 把新决议、新术语、新案例分段嵌入

## M3 上线最小实现
- 嵌入模型：本地 BGE-M3 / Qwen-Embedding（中文友好）
- 向量库：FAISS 单机（M3）→ Milvus（M4）
- 检索结果**强制**过 prompt-injection-scan

## 待开发清单
- [ ] embed pipeline
- [ ] 向量库部署
- [ ] search / ingest 端点
- [ ] 注入扫描集成
- [ ] 内容更新 SLA：决议 24h / Wiki 1 周

## 自审清单
- [ ] 任何 hit 不返回 L3/L4 字段值
- [ ] ingest 过滤 PHI（接 mcp-phi-detector）
- [ ] 检索日志落 mcp-audit-log
