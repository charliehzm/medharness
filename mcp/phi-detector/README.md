# mcp-phi-detector

> 实时 PHI / PII 检测的 MCP server。Hook 与 Skill 的兜底闸门。

## 职责
- 输入：任意文本 / JSON 载荷
- 输出：命中清单（type / span / confidence / suggested_action）
- 失败：fail-closed（返回错误时调用方按"疑似命中"处理）

## 检测层
1. **Pass 1 规则层**：CN-ID / CN-phone / CN-bank / email / HIPAA-18-identifiers / 医院 MRN / 自定义术语
2. **Pass 2 分类器层**：本地 Qwen-1.8B / 微调 BERT；CPU 即可
3. **Pass 3 仲裁**：两层结果合并，规则与分类器不一致时按 OR 处理（宁可误报）

## 接口

### `detect`
```jsonc
// request
{
  "text": "string OR json-serialized payload",
  "context": {
    "change_id": "optional",
    "tier_hint": "L1|L2|L3|L4"   // 调用方期望的等级，仅作为参考
  }
}

// response
{
  "hits": [
    {"type": "CN-Phone", "span": [12, 23], "confidence": 0.98, "suggested": "desensitize"},
    {"type": "free-text-PHI", "span": [40, 90], "confidence": 0.81, "suggested": "review"}
  ],
  "summary": {
    "total_hits": 2,
    "max_confidence": 0.98,
    "blocking_recommendation": true
  }
}
```

### `health`
返回 server 状态、规则集 hash、分类器版本。

## 部署
- M2：单实例 Docker，与开发机同子网
- M3+：内网 K8s 部署，HA

## 配置
- `rules.yml`：规则集（CN-ID 正则、医院 MRN 模式等）
- `classifier.yml`：分类器路径、阈值
- `audit.yml`：审计落盘位置

## 待开发清单（M2）
- [ ] 实现规则层 + 分类器层 + 仲裁
- [ ] 输出与 Claude Code Hook 协议对齐
- [ ] 单测覆盖 18 类 HIPAA 标识符
- [ ] 红队样本集 ≥ 200 条
- [ ] 性能：P99 ≤ 50ms（单 prompt ≤ 2000 token）

## 自审清单
- [ ] 服务自身日志不打印命中的原始字符串（避免二次泄漏）
- [ ] 规则与分类器都升级时 freeze 一次 rules+classifier 版本号，挂入 AUDIT_BUNDLE
