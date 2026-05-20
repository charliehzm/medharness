# mcp-vector-db

> 项目代码 / Spec / Memory 的向量检索服务（M4 上线）。

## 职责
- 对 OpenSpec specs / Memory artifacts / 已归档 PRD_SUMMARY 做嵌入
- 提供相似度检索（M4 默认 BGE-M3，cosine）
- 与 mcp-internal-kb 互补：KB 是结构化 + 文档级；vector-db 是片段级语义检索

## 嵌入策略
- 分块：自然段 + 滑窗 128 tokens
- 模型：BGE-M3（M4 起，本地部署）
- 维度：1024
- 索引：Milvus（HNSW）

## 接口

### `index_document`
```jsonc
{
  "id": "...",
  "category": "spec | memory | prd-summary | code-comment",
  "text": "...",
  "metadata": {"change_id": "...", "tier": "L1|L2"}
}
```
**前置**：text 必须先通过 phi-detector + injection-scan。

### `search`
```jsonc
// request
{"query": "...", "top_k": 8, "filter": {"category": "..."}}

// response
{"hits": [{"id": "...", "score": 0.x, "snippet": "...", "metadata": {...}}]}
```

### `reindex`
全量重建。M-Curator 周扫触发。

## 待开发清单（M4）
- [ ] Milvus 部署
- [ ] BGE-M3 模型部署
- [ ] index/search/reindex 三端点
- [ ] PHI/注入前置过滤
- [ ] 健康检查 + 监控

## 自审清单
- [ ] L3/L4 内容禁止入向量库
- [ ] 检索 hits 上下游过注入扫描
- [ ] 索引文件落审计（哈希 + 时间戳）
