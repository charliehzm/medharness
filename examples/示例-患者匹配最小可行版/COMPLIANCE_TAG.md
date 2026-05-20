# COMPLIANCE_TAG · 患者匹配最小可行版

> Step 0 合规预检产物。在任何代码动手前必须签字。

---

## 1. 数据字段分级

| 字段 | 内容 | 分级 | 处理 |
|---|---|---|---|
| `patient_name` | 真实姓名 | **L4** | 入 prompt 前必 desensitize |
| `cn_id` | 中国身份证 | **L4** | 同上 |
| `cn_phone` | 中国手机号 | **L4** | 同上 |
| `cn_mrn` | 本院病案号 | **L4** | 同上 |
| `match_id` | 内部统一 ID（脱敏后） | L2 | 可入 prompt |
| `confidence` | 匹配置信度 0-1 | L1 | 公开 |

## 2. 模型 allowlist

| 用途 | 模型 | 允许？ |
|---|---|---|
| 匹配决策 | Qwen 32B 本地 | ✅ |
| Code Review | DeepSeek V4-Pro 私有 | ✅ |
| 合规审查（异构必须） | Claude Opus 4.7（境外） | ✅ 但仅零 PHI 抽象设计 |
| 公共 DeepSeek API | — | ❌ 禁 |
| 公共 GPT-4 | — | ❌ 禁 |

## 3. 测试数据合规

- 数据集名：`synthetic_patients_5k.csv`
- 生成方法：`test-data-generation` Skill + Faker zh_CN
- 真实反演风险：经指纹核验 = 0
- 来源声明：100% 合成，无任何生产采样

## 4. 审计要求

- 每次匹配请求：哈希上链
- 保留期：≥ 6 年（HIPAA 标准）
- 存储：WORM ClickHouse 本地 + OSS Object Lock（商业版）

## 5. 签字

| 角色 | 姓名 | 日期 |
|---|---|---|
| 提案人 | _________ | 2026-__-__ |
| Compliance Officer | _________ | 2026-__-__ |
| 技术 Lead | _________ | 2026-__-__ |

未三方签字，禁止进入 Step 1 PRD。
