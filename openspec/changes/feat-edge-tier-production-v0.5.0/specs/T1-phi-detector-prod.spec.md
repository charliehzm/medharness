# Spec · T1 · phi-detector v3 真集成 Presidio

> 任务 T1 完整规格。codex 实现前**必读**。

---

## Purpose

把 `mcp/phi-detector/server_v3.py` 从 stub（`{"type":"STUB"}`）改为真用 Microsoft Presidio AnalyzerEngine。
中文医疗 recall ≥ 92% on 合成 corpus。

---

## Inputs

- `text: str` · 待检测文本（最长 8192 chars）
- `language: str = "zh"` · 语言代码（zh / en）
- `score_threshold: float = 0.6` · presidio confidence 阈值
- `entities: list[str] | None` · 限定检测类型（None = 全检）

## Outputs

```python
{
    "spans": [
        {
            "start": int,        # 字符偏移
            "end": int,
            "type": str,         # cn_id / cn_phone / cn_mrn / 中文姓名 / ...
            "score": float,      # 0.0-1.0
            "text_sha256": str,  # 仅哈希，不返回原文（脱敏 by default）
        }
    ],
    "stats": {
        "recall_estimate": float,   # 基于 score 分布的本次估计
        "duration_ms": float,
    }
}
```

---

## Constraints

- C1 · 输入文本**永不在响应里裸返回** — spans 仅含偏移 + 类型 + 哈希
- C2 · 单次推理 < 100ms（CPU · 1K chars 文本）
- C3 · 内存峰值 < 500MB / 进程
- C4 · 启动时间 < 10s（含 spaCy 模型加载）
- C5 · 离线运行（无外网调用）
- C6 · 31 fields.yml 必须全加载（不跳过任何 recognizer）

---

## Architecture

```
text → AnalyzerEngine.analyze()
         ├─ presidio default recognizers（en）
         ├─ custom CN recognizers（zh, 11 个）
         └─ context-aware post-processing（6 规则）
              ├─ Luhn check（cn_id / cn_bank）
              ├─ 占位符 suppress
              ├─ 日志时间戳 demote
              ├─ 姓名邻近加权（医生/患者 加 / 员工 减）
              ├─ 60s session 缓存
              └─ CN-Bank 严格化
       ↓
spans → text_sha256 替换 → response
```

---

## Custom CN Recognizers（11 个）

| Recognizer | Pattern | Context boost |
|---|---|---|
| `cn_id` | 18 位身份证（含校验） | 姓名邻近、"身份证" 关键词 |
| `cn_phone` | 11 位手机号（含网段） | "手机/电话" 关键词 |
| `cn_mrn` | `^[A-Z]{2}\d{8}$` 等本院规则 | "病案号/住院号" |
| `cn_bank` | 16-19 位银行卡（Luhn） | "卡号/银联" |
| `cn_name` | spaCy NER PER + 中文姓氏白名单 | "患者/医生/姓名" |
| `cn_address` | 省市区 + 街道关键词 | "住址/籍贯" |
| `cn_passport` | E + 8 位数字 | "护照" |
| `cn_hk_id` | HKID 字母+数字 | — |
| `cn_drivers_license` | 18 位（同 cn_id 但 context 不同） | "驾驶证" |
| `cn_disease_code` | ICD-10 / ICD-11 codes | "诊断" |
| `cn_drug_code` | 国药准字 + 编号 | "药品/处方" |

每 recognizer 一个 Python class in `mcp/phi-detector/recognizers/cn_*.py`，
继承 `presidio_analyzer.PatternRecognizer` 或 `EntityRecognizer`。

---

## 6 上下文规则（post-processing）

### 1. Luhn check
- `cn_id` / `cn_bank` 必过 Luhn → 不过则 score *= 0.3

### 2. 占位符 suppress
- 已知占位列表：`110101199001011234` / `13800138000` / `ID-XXX` / `<phi>` / `${phi}` …
- 命中 → score = 0

### 3. 日志时间戳 demote
- 前后 50 chars 含 log level 关键词（INFO / ERROR / DEBUG / WARN）
- → 该 span score *= 0.2

### 4. 姓名邻近加权
- 前后 20 chars 含 "患者/病人/医生/护士" → score *= 1.3
- 前后 20 chars 含 "员工/用户/Co-Author/作者/contributor" → score *= 0.5

### 5. 60s session 缓存
- 同 prompt 60s 内重复扫 → 直接复用结果
- 用 `text_sha256` 作 key
- LRU 限 10k entries

### 6. CN-Bank 严格化
- 必须 16-19 位 + 在已知 BIN 前缀（中国主要银行）+ 过 Luhn
- 否则 demote 到 cn_id 类别 reconsider

---

## fields.yml schema

```yaml
fields:
  - id: cn_id
    presidio_entity: CN_ID
    score_min: 0.6
    must_pass_luhn: true
    context_boost:
      keywords: [身份证, ID]
      window: 20
  - id: cn_phone
    presidio_entity: CN_PHONE
    score_min: 0.7
    pattern: ^(13|14|15|16|17|18|19)\d{9}$
    context_boost:
      keywords: [手机, 电话, 联系]
      window: 20
  # ... 31 条
```

---

## Acceptance criteria

- AC1 · recall ≥ 92% on `tests/red-team-drills/fixtures/synthetic_phi_corpus.jsonl`（≥ 200 用例）
- AC2 · 误判率（FP） ≤ 15% on negative corpus（≥ 100 用例 · 日志、代码、文档）
- AC3 · 单 1K-char 推理 < 100ms（CPU · macOS M-series / Linux x64）
- AC4 · 启动 < 10s
- AC5 · 单测覆盖率 ≥ 80%（`mcp/phi-detector/`）
- AC6 · drill 1 CI gate 通过：`python tests/red-team-drills/check_recall.py --min 0.92`

---

## Non-goals（本任务不做）

- 训练好的微调模型（属商业版）
- 实时 streaming 检测（同步 batch 即可）
- GPU 推理（CPU only）
- 上下文窗口跨段（同一 prompt 限 8192 chars）

---

## Test fixtures（codex 需扩充）

当前 `tests/red-team-drills/fixtures/synthetic_phi_corpus.jsonl` 只 4 条。
T1 实施时扩到 ≥ 200 用例，覆盖：

- 11 个 CN recognizer 各 ≥ 10 正例 + 5 负例
- 6 上下文规则各 ≥ 5 用例
- 8 个 false positive 历史踩坑（日志时间戳 / 占位符 / 测试身份证 / ...）

新 fixtures 必经 `test-data-generation` Skill + 指纹核验。

---

## Dependencies

- 上游：[microsoft/presidio](https://github.com/microsoft/presidio) v2.2+
- 模型：`zh_core_web_sm`（85MB · spaCy 中文小模型）
- requirements.txt 已含 presidio-analyzer / presidio-anonymizer / spacy / faker

---

## Migration / Backward compat

- v0.1 的 phi-detector stub 输出格式简化：`[{"start","end","type","score"}]`
- v0.5 新增 `text_sha256` 字段 + `stats` 包装
- 调用者（client / Hook）需适配 → 在 T5 drill 2 同步更新

---

## Implementation hints（给 codex）

```python
# mcp/phi-detector/server_v3.py · 雏形（仅示意）
from presidio_analyzer import AnalyzerEngine
from mcp.phi_detector.recognizers import load_cn_recognizers
from mcp.phi_detector.postprocess import apply_context_rules

class PhiDetectorV3:
    def __init__(self, fields_path="fields.yml"):
        self.engine = AnalyzerEngine()
        for r in load_cn_recognizers(fields_path):
            self.engine.registry.add_recognizer(r)
        self._cache = LRUCache(maxsize=10000)
    
    def detect(self, text, language="zh", score_threshold=0.6):
        # 1. 缓存命中
        key = sha256(text).hexdigest()
        if hit := self._cache.get(key):
            return hit
        # 2. analyze
        raw = self.engine.analyze(text, language=language)
        # 3. post-process
        spans = apply_context_rules(text, raw, score_threshold)
        # 4. hash + cache
        result = {"spans": [{"start":s.start, "end":s.end, "type":s.entity_type,
                              "score":s.score, "text_sha256":sha256(text[s.start:s.end])}
                            for s in spans],
                  "stats": {...}}
        self._cache[key] = result
        return result
```

详细实现见 codex 接手后产出。

---

## Risks

| 风险 | 对冲 |
|---|---|
| Presidio 中文模型 recall 低 | 31 recognizer + 6 上下文规则弥补；M2 内向上游提交 PR |
| 大文本性能问题 | 限 8192 chars + 缓存 |
| ICD-10/11 recognizer 误识别普通数字 | context_boost 必须严格 |
| 启动时间长 | spaCy 模型 lazy load + 内存 mmap |
