# 架构 × 开源依赖图

> 6 层架构 × 上游开源项目 × 我们的医疗专属层。
> **设计原则**：站在巨人肩膀上，不重造轮子。垂直深做医疗。

---

## 1. 6 层架构 × 开源 vendor

```
┌─────────────────────────────────────────────────────────────────────────┐
│ L6 治理层                                                                │
│   双委员会 + Skill Owner 制                                              │
│   我们独有 · 无开源替代                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ L5 合规层（横切）                                                        │
│   ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐             │
│   │ phi-detect  │  │ desensitize       │  │ model-router   │             │
│   │ 上游: Presidio│  │ 上游: cryptography│  │ 上游: 自研     │             │
│   │ 加: 中文 31  │  │ 加: KMS 集成      │  │ 加: 医疗 allowlist│           │
│   │  fields.yml │  │                   │  │                │             │
│   └─────────────┘  └──────────────────┘  └────────────────┘             │
│                                                                          │
│   ┌─────────────────┐  ┌─────────────────────┐                          │
│   │ audit-log       │  │ prompt-injection-scan│                         │
│   │ WORM 哈希链     │  │ 上游: 自研 + RAG分类 │                         │
│   │ 我们独有        │  │ 加: 医疗专属规则     │                         │
│   └─────────────────┘  └─────────────────────┘                          │
├─────────────────────────────────────────────────────────────────────────┤
│ L4 SOP 层                                                                │
│   12 步主通道 + 5 步 micro 通道                                          │
│   上游: github/spec-kit · Fission-AI/OpenSpec                            │
│   加: Step 0 合规预检 + Step 10 合规 Gate + Step 12 审计冻结              │
├─────────────────────────────────────────────────────────────────────────┤
│ L3 Skill 层                                                              │
│   23 Skill（5 合规 + 16 通用 + 2 micro 别名）                            │
│   上游: anthropics/skills                                                │
│   加: 5 医疗专属 + routing-evals.json 反哺                               │
├─────────────────────────────────────────────────────────────────────────┤
│ L2 Harness 层                                                            │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│   │ Orchestrator │  │ Sub-agent×6  │  │ Tiered Memory│                  │
│   │ Claude Code  │  │ 我们独有      │  │ claude-mem   │                  │
│   └──────────────┘  └──────────────┘  └──────────────┘                  │
│   ┌──────────────┐  ┌──────────────────────────────────┐                │
│   │ Hook×9       │  │ MCP×8                            │                │
│   │ Claude Code  │  │ 上游: modelcontextprotocol       │                │
│   │  hooks system│  │ 加: 8 件医疗专属                  │                │
│   └──────────────┘  └──────────────────────────────────┘                │
├─────────────────────────────────────────────────────────────────────────┤
│ L1 模型层                                                                │
│   编码 / Review / 架构 / 长文 / 脱敏 / 合规独立                          │
│   上游: Anthropic Claude / DeepSeek / Qwen / 其他                        │
│   加: 模型可用性矩阵（按数据分级 + 行业 allowlist）                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 关键上游项目

| 项目 | 我们用 | 我们加 |
|---|---|---|
| **[microsoft/presidio](https://github.com/microsoft/presidio)** | PHI 检测底层 | 中文医疗 recognizer + 31 fields.yml + 上下文规则 |
| **[Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)** | Spec 框架 | 12+5 步双通道 SOP |
| **[github/spec-kit](https://github.com/github/spec-kit)** | 三段式 spec 实践 | verify / compliance gate / audit freeze 扩展 |
| **[anthropics/skills](https://github.com/anthropics/skills)** | Skill 设计范式 | 5 医疗专属 + routing-evals.json |
| **[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)** | MCP 框架 | 8 件医疗合规专属 server |
| **[shubh2016shiv/hipaa-medical-phi-deidentifier](https://github.com/shubh2016shiv/hipaa-medical-phi-deidentifier)** | HIPAA 18 标识符参考 | 同上 + 中国 PIPL 字段 |
| **[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)** | Memory 系统范式 | fact/inference 双层 + derives_from 追溯 |
| **[affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code)** | Harness 参考 | 加合规闸门 + 异构性强制 |

---

## 3. 我们独有的核心 IP（无开源替代）

1. **12+5 步双通道 SOP**：速度 / 合规双轨
2. **异构性强制 Compliance-Agent**：厂商家族 + 完整 model_id 双校验
3. **AUDIT_BUNDLE 哈希链 + 6 年 WORM + 配对销毁 KMS**
4. **三视角穿透审计法**：consultant / medical / architect 视角交叉
5. **M1-M6 沙盘模拟法**：里程碑前用合成案例验证
6. **routing-evals.json 反哺机制**：Skill 触发准确率持续 evolve
7. **90 天督导 + 主理人接棒培训方法论**
8. **PIPL + 数据安全法 + 健康医疗数据安全指南** 本土化合规层

---

## 4. 数据流（合规视角）

```
用户输入
   │
   ▼
[Hook · UserPromptSubmit]
   ├─→ mcp-phi-detector → 命中 PHI? ──Y──→ 阻断 / 告警
   │                                ─N──→ 通过
   ▼
[Skill 系统]
   ├─→ Sub-agent × 6 调度（异构性强制）
   │
   ▼
[mcp-desensitize] PHI → 脱敏 + 反向映射表（KMS 加密）
   │
   ▼
[mcp-model-router] 按 COMPLIANCE_TAG.md 的 allowlist 路由
   │     ├─→ L1 公开数据 → 公共 API
   │     ├─→ L2-L3 内部 → 公共 API（已脱敏）
   │     └─→ L4 PHI → 私有部署 only
   ▼
[LLM 推理]
   │
   ▼
[Hook · ToolUse / Stop]
   ├─→ mcp-audit-log（哈希链上链 · WORM）
   │
   ▼
[AUDIT_BUNDLE 打包] · 6 年保留
```

---

## 5. 模块依赖矩阵

| 层 | 依赖于 | 被依赖 |
|---|---|---|
| L1 模型 | （外部） | L2 Harness |
| L2 Harness | L1 模型 + MCP servers | L3 Skill / L4 SOP |
| L3 Skill | L2 Harness + Memory | L4 SOP |
| L4 SOP | L3 Skill + L5 合规 | 业务 change |
| L5 合规（横切） | L1-L4 任何动作 | 全部 |
| L6 治理 | L4 SOP + L5 合规 | License / RFC / 决策日志 |

**承重墙**：
- L4 SOP 的 12 步骨架不动（micro 通道是补充，不是替换）
- L5 合规的 5 红线不动
- L1 模型的"按 allowlist 路由"不动

**热更新区**：
- L3 Skill 的 SKILL.md 措辞 / trigger / references
- L5 合规的 fields.yml 字段（增加 OK，删除需双委员会）
- L1 模型的 allowlist（增加 maintainer 决，删除双委员会）

---

## 6. 演进路径

```
v0.1 (current)  ← 6 层骨架，MCP 是 v2 占位
v0.2            ← L5 真集成（Presidio + 中文 recognizer）
v0.3            ← L2 Compliance-Agent 异构 + WORM 真后端
v1.0 (M6)       ← MCP 8 件套全部"非占位" + 商业版起步
v2.0 (M12)      ← 国际化 + 联盟 + 大客户案例反哺
```

---

## 7. License 兼容性

| 上游 | License | 我们 vendor 方式 | 兼容 |
|---|---|---|---|
| presidio | MIT | pip 依赖 | ✅ |
| spec-kit | MIT | 思想借鉴 | ✅ |
| OpenSpec | MIT | 思想借鉴 | ✅ |
| anthropics/skills | MIT | SKILL.md 格式借鉴 | ✅ |
| MCP servers | MIT | 接口借鉴 | ✅ |
| claude-mem | MIT | 思想借鉴 | ✅ |

所有上游均 MIT 兼容，可放心 vendor / 借鉴 / 商业。
我们的代码 Apache 2.0 比 MIT 多专利保护，对企业用户友好。

---

## 8. 一句话

> 我们不是从零设计架构。
> 是把医疗特有的"PHI 永不裸入 + 异构合规 + 6 年审计"叠加到通用 AI Coding 生态上。
>
> 让通用工具能干医疗 SaaS 的活。
