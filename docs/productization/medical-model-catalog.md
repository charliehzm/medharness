# 医疗大模型选型与接入

> **状态**：DRAFT · 数据时效 **2026-05**（开源部分取自 Hugging Face API，境内商用取自公开检索）。
> **依据**：[product-requirements.md](product-requirements.md) G1 安全 / G2 划算 / G4 稳定 · [console-product-design.md §5.5 接入](console-product-design.md) · 重设计 RFC [gateway-substrate-selection.md §C/§F](../architecture/gateway-substrate-selection.md)。
> **一句话**：MedHarness 本身**不绑定**某个医疗模型——它给客户一份**按通道（合规）筛过**的可选清单 + 标准接入方式。"接什么、怎么接、进哪个通道"由本文定义。
> ⚠️ **务必复核**：模型版本、私有部署授权、no-retention/境内驻留合同等以**选型时厂商正式确认**为准；下表是 2026-05 快照与起步建议，非长期承诺。

---

## 1. 选型铁律：通道（合规）先于质量

在医疗网关里，第一道筛子不是"哪个聪明"，而是"**这数据能去哪**"。先定通道资格，再比质量：

| 通道 | 数据 | 可用模型范围 |
|---|---|---|
| **敏感通道**（L3-L4，**不出境**） | 含 PHI | 仅：① 客户内网**私有部署**模型 ② 境内厂商 API 且签 **no-retention/no-training + 境内驻留**合同 |
| **常规通道**（L1-L2 / 已脱敏，境内低成本池） | 无 PHI | 境内 API，广而便宜 |
| **境外**（GPT/Claude/Gemini/Med-PaLM…） | **仅脱敏后** | **碰 PHI 一律禁**；再强也只能进脱敏后常规通道，且 allowlist + region 严格 |

> 推论：**境外医疗模型（如 Med-PaLM/MedGemma）质量再高，碰患者数据也用不了**——PIPL/数据安全法硬线。

---

## 2. 模型菜单（按"类别 × 通道"）

### A. 境内通用强模型（主力工作马）
DeepSeek（V/R 系列）· 通义千问 Qwen · 智谱 GLM · 豆包 Doubao · Kimi · 文心 ERNIE
- API → **常规通道**（便宜池主力）；开源/私有版装内网 → **敏感通道**。

### B. 境内医疗专用（临床准确性，2026 实况）
| 厂商/模型 | 信号（2026-05） | 接入形态 |
|---|---|---|
| **百川 Baichuan M2/M3 Plus + 32B** | 境内医疗**领头羊**，主打**低幻觉**；宣称 32B 可一键部署 | 商用 API；**若 32B 可私有授权 → 敏感通道** |
| **讯飞星火医疗 / 晓医** | 医疗深耕 | 商用 API |
| **蚂蚁 / 阿里（健康管家向）** | 声量领先 | 商用 API |
| 国产"医疗十强" | 36氪已盘点 | 选型时拉全表对比 |
> ⚠️ "超越 GPT/碾压 OpenAI"为厂商口径，**必须独立医疗红队验证**（见 §5）。

### C. 开源可私有部署医疗（敏感通道核心 · HF 可验证）
能用 vLLM/SGLang 装进客户内网 = **天然不出境**：

| 模型 | 规模 | 特点 |
|---|---|---|
| **Lingshu 灵枢** | 7B / 32B | 医疗**多模态**（含影像）→ 对应 DICOM/影像场景 |
| **HuatuoGPT-o1** | 7B/8B/72B | 中文医疗**推理**；另有 **HuatuoGPT-Vision**（多模态） |
| **II-Medical** | 8B / 32B | 医疗推理，口碑高 |
| **Meditron3-8B**（EPFL） | 8B | 强开源医疗（英文为主） |
| **Bio-Medical-Llama-3-8B**（+多模态版） | 8B | Llama-3 医疗 |
| **ClinicalGPT-base-zh** | — | 中文临床 |

### D. 境外（仅脱敏后常规通道）
GPT-4o/o 系列 · Claude · Gemini；医疗 Med-PaLM 2 / MedGemma / MedLM。默认**不碰 PHI**。

---

## 3. 接入方式（落到 new-api 底座 + 通道扩展）

| 模型类别 | new-api 接法 | 通道 |
|---|---|---|
| 开源医疗私有部署（Lingshu / HuatuoGPT-o1 / II-Medical / Meditron3） | **vLLM/SGLang/Ollama 起 OpenAI 兼容端点 → 自定义 upstream 渠道** | 敏感通道（不出境） |
| 百川 32B（若可私有授权） | 同上私有部署 | 敏感通道 |
| 百川 / 讯飞医疗 **API** | OpenAI 兼容 / 原生渠道 | 常规（脱敏后）或敏感（须 no-retention + 境内合同） |
| DeepSeek / Qwen / GLM / 豆包 境内 | new-api 原生渠道 | 常规通道便宜池 |
| 境外 GPT/Claude/Gemini | new-api 原生渠道 | 仅脱敏后常规通道 |

**每个渠道必须挂的扩展属性**（见 [console-product-design.md §5.2](console-product-design.md)）：
`数据等级上限 / 通道(常规·敏感) / region(境内外) / 留存策略(no-retention) / 单价 / 权重`
→ 一次配置同时管 **路由（安全）+ 成本（划算）+ 合规**。

**多渠道择优**：同一能力挂多个 provider（如 DeepSeek 火山/官方/私有），按价/延迟/健康加权（划算）；故障切换**仍限 allowlist 内**（稳定）。

---

## 4. 起步 allowlist 推荐（≤30 人医疗 · 示例，非写死）

| 模型 | 类型 | 接入 | 通道 | region | 留存 | 数据等级上限 | 用途 |
|---|---|---|---|---|---|---|---|
| deepseek（境内 API） | 通用 | 原生渠道 | 常规 | 境内 | no-retention | L2 | 日常 / 便宜池主力 |
| qwen-max（境内 API） | 通用 | 原生渠道 | 常规 | 境内 | no-retention | L2 | 日常 |
| Qwen2.5/3（私有 vLLM） | 通用 | 自定义 upstream | 敏感 | 私有 | 不外发 | L4 | 含 PHI 通用 |
| **Lingshu-32B**（私有 vLLM） | 医疗·多模态 | 自定义 upstream | 敏感 | 私有 | 不外发 | L4 | 含 PHI · 影像 |
| **HuatuoGPT-o1-8B**（私有 vLLM） | 医疗·推理 | 自定义 upstream | 敏感 | 私有 | 不外发 | L4 | 含 PHI · 临床问答 |
| 百川医疗 API | 医疗 | 原生渠道 | 常规（脱敏后） | 境内 | 须合同 | L2 | 脱敏后增强；如签私有+合同可升敏感 |
| claude-sonnet / gpt-4o | 通用 | 原生渠道 | 常规（脱敏后） | 境外 | provider 条款 | L2 | 可选 · **默认禁 PHI** |

---

## 5. 医疗专属注意（最易被忽略）

1. **接医疗模型 = 放大幻觉风险 → 出站闸门是前置条件**：医疗专用模型**不等于不幻觉**，幻觉医嘱危害更大。G1 的**出站响应安全检查（PHI 回流 / 幻觉医嘱 / 有害）必须先就位**才接医疗模型；厂商"低幻觉"宣传与我们的出站复核**互补不替代**。
2. **多模态 = 影像 PHI 场景**：Lingshu / HuatuoGPT-Vision 等多模态模型对应 DICOM/影像，但**多模态 PHI 脱敏是最难的一环**（影像 burned-in 文本、元数据）；接入前该能力要先到位。
3. **NMPA / 医疗器械（SaMD）边界**：模型输出用于诊断/治疗决策可能触监管。网关**只路由不做临床决策**；合同/审计写明"输出仅供医务人员参考，临床责任在客户"。
4. **境内 API 进池硬条件**：no-retention / no-training + 境内驻留合同（RFC §F 已锁）。
5. **PHI lane 最干净路径 = 开源模型私有部署**；商用 API（含百川）碰 PHI 必须先清私有授权 / 境内驻留 / 合同。

---

## 6. 模型准入流程（Model Onboarding · 上 allowlist 前）

```
① 医疗基准评测（MedQA / CMB / CMExam / 客户临床场景集）
② 红队：幻觉医嘱 / 有害输出 / 注入鲁棒性
③ 合规核验：私有部署授权 or no-retention+境内驻留合同
④ new-api 配渠道 + 挂扩展属性（通道/region/留存/数据等级上限/单价/权重）
⑤ 上 allowlist（研发负责人审批 · 见治理矩阵）
⑥ 全程落审计；上线后纳入出站幻觉/有害持续监测
```

---

## Sources（2026-05 · curl 实取）
- Hugging Face API：[Lingshu-32B](https://huggingface.co/lingshu-medical-mllm/Lingshu-32B) · [HuatuoGPT-o1-72B](https://huggingface.co/FreedomIntelligence/HuatuoGPT-o1-72B) · [II-Medical-32B](https://huggingface.co/Intelligent-Internet/II-Medical-32B-Preview) · [Meditron3-8B](https://huggingface.co/EPFLiGHT/Meditron3-8B) · [Bio-Medical-Llama-3-8B](https://huggingface.co/ContactDoctor/Bio-Medical-Llama-3-8B) · [ClinicalGPT-base-zh](https://huggingface.co/medicalai/ClinicalGPT-base-zh)
- 公开检索（境内商用，2026）：36氪《2026 国内最值得期待的十个医疗大模型》· 新浪财经《百川 M3 Plus》· 《百川 M2 Plus 幻觉率降到 DeepSeek 三成》· [百川智能](https://www.baichuan-ai.com) · 讯飞医疗
> 境内商用部分含厂商宣传口径，能力以独立评测（§5/§6）为准。
