# Changelog

> 遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) + [SemVer 2.0](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0-alpha] - 2026-05-__

### Added · 首发

- 6 层架构骨架：L1 模型 / L2 Harness / L3 Skill / L4 SOP / L5 合规 / L6 治理
- **23 Skill** SKILL.md（合规 5 / 通用 16 / micro 别名 2）
- **6 Sub-agent**：PM / Coder / Reviewer / Compliance / Memory-Curator / Data-Steward
- **8 MCP server** v2 实现（占位 + 本地 demo）：
  - phi-detector / desensitize / model-router / audit-log
  - internal-kb / vector-db / ci-trigger / pm-bridge
- **9 Hook 脚本** warn 默认（block 可配）
- **12+5 步双通道 SOP** 全文
- **AUDIT_BUNDLE schema** + snapshot_packer 实现
- **31 fields.yml**（中文医疗字段，Presidio 兼容）
- **9 培训文档** + 90 天督导方法论
- 完整示例 change `示例-患者匹配最小可行版/` 可端到端跑通
- `dryrun_e2e_v2.sh` 自动 install + 自动跑通 Step 0-12
- `tools/customize.py` 交互式向导

### Documented

- README 5 分钟上手路径
- CONTRIBUTING.md 含合规自检 5 问
- SECURITY.md PHI 泄漏 / 审计绕过披露通道
- 6 层架构文档
- 12 步 SOP 文档
- 与开源生态依赖关系（Presidio / OpenSpec / Spec-Kit / Anthropic Skills / MCP）

### Known Limitations

- 公共 LLM API 阶段（M1-M5）依赖 `phi-desensitize` 前置
- Hook 技术上可绕过；社区版用 warn 默认
- Presidio 中文医疗 recognizer 召回率约 92-96%
