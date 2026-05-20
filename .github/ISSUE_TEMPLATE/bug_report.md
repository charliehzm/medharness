---
name: Bug Report
about: 报告 MedHarness 的 bug（**勿在此提交 PHI 泄漏 / 合规漏洞** → 走 SECURITY.md）
title: '[BUG] '
labels: bug, triage
assignees: ''
---

## 描述
简洁说明 bug 是什么。

## 复现步骤
1. 跑 `xxx`
2. 改 `yyy`
3. 看到 `zzz`

**注意**：不要在复现步骤里粘真实 PHI 数据。用合成示例。

## 期望行为
应该发生什么？

## 实际行为
实际发生了什么？

## 环境
- MedHarness 版本：`v0.x.x`
- OS：macOS / Linux / WSL
- Python：3.x.x
- Claude Code 版本（如适用）：
- 模型：DeepSeek / Claude / Qwen / 其他

## 相关日志 / AUDIT_BUNDLE 片段
```
（脱敏后粘贴）
```

## 自检
- [ ] 我已读 README 的 5 分钟上手
- [ ] 我已跑 `dryrun_e2e_v2.sh` 验证基础环境
- [ ] 我不是在报告合规漏洞（合规漏洞走 `security@medharness.io`）
