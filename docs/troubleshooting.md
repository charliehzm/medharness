# Troubleshooting · 内测 5 分钟踩坑指南

> D5 内测期间收集到的 Top 10 问题。
> 没找到你的问题？开 [Issue](https://github.com/charliehzm/medharness/issues/new/choose) 或 [Discussion](https://github.com/charliehzm/medharness/discussions)。

---

## 1. dryrun 卡在 `Step -1` venv 创建

**症状**：`python3 -m venv .venv` 报 `command not found` 或权限错误。

**修复**：
```bash
# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv

# CentOS/RHEL
sudo dnf install python3.11
```

确认版本 ≥ 3.10：
```bash
python3 --version
```

---

## 2. `pip install` 装 `presidio-analyzer` 卡 `spacy` 模型

**症状**：安装慢（10+ min）或失败。

**原因**：spacy 默认下载多语言模型，慢。

**修复**：装完依赖后单独下中文模型：
```bash
python -m spacy download zh_core_web_sm
```

CI 中跳过：用 `--no-spacy-models` 标志（v0.2.0 起）。

---

## 3. `customize.py` 警告"编码主力 与 合规 Agent 相同"

**症状**：向导退出码 2。

**原因**：异构性强制——合规审查模型必须与编码主力**不同厂商家族**，否则等于"自证清白"。

**修复**：
- 编码主力选 Claude → 合规 Agent 必须选 DeepSeek / Qwen / GPT 等不同家族
- 或反之

理论背景：见 [governance/v2.1-变更清单.md] 中的"异构性强制"条目（vbecoding 内部经验）。

---

## 4. `dryrun_e2e_v2.sh` 在 macOS 报 `bash 3.x` 语法错误

**症状**：`${m,,}` 等 bash 4+ 语法报错。

**修复**：本仓库的 shell 脚本已经避开 bash 4+ 语法（兼容 macOS 系统 bash 3.x）。
如你看到该错误，请提 issue 附上 `bash --version` 输出。

---

## 5. AUDIT_BUNDLE 超过 20MB

**症状**：tar.gz 文件超 20MB。

**原因**：prompts/ 子目录未 gzip。

**修复**（v0.2.0 起自动处理）：
```bash
find AUDIT_BUNDLE_*/prompts -name '*.jsonl' -exec gzip {} \;
```

期望大小：< 20MB（v2.2 NPS 案例做到 ~10MB）。

---

## 6. Hook 误判（PHI 误报）

**症状**：phi-detector 把日志时间戳 / 占位符 / IPv4 / 测试数据当作 PHI 阻断。

**原因**：v1 Hook 上下文不足。

**修复**：
- 用 `phi-detector` v3：6 条规则优化（Luhn + 占位符 suppress + 日志时间戳上下文 + 姓名邻近 + 60s session 缓存 + CN-Bank 严格）
- 升级路径：`mcp/phi-detector/server_v3.py` 已为默认实现
- 误判率应从 ~66% 降到 < 15%

红队演练验证：`bash tests/red-team-drills/run_all.sh`。

---

## 7. PR 模板的"合规自检 5 问"我答不上

**症状**：不确定怎么填。

**修复**：
- 看 [docs/compliance-checklist.md](compliance-checklist.md) 案例
- 或直接在 PR 描述里写"@medharness-org/compliance review 需要协助"
- 不要瞎填——错误填写是合规违规

---

## 8. `mcp-model-router` 阻断我所有调用

**症状**：所有 LLM 调用返回 403。

**原因**：你的 `COMPLIANCE_TAG.md` 没签字 / model allowlist 为空。

**修复**：
1. 跑 `python tools/customize.py` 完成项目档案
2. 检查 `examples/<your-change>/COMPLIANCE_TAG.md` 是否三方签字
3. 看 router 日志：`tail -f .audit/router_decisions.jsonl`

---

## 9. Compliance-Agent 跑得太慢

**症状**：Step 10 卡 30+ 分钟。

**原因**：Compliance-Agent 默认同步审查；如审查面太广，会慢。

**修复**：
- 切异步预审模式（M4 起默认）
- Gate 仅做最终裁决；中风险并行处理

---

## 10. 我想关 Hook（暂时）

**回答**：**不可以**。

关 Hook = 合规违规 → 需双委员会（技术 + 合规）签字。
紧急情况联系 `security@medharness.io`。

---

## 找不到答案？

1. 搜 [Discussions Q&A](https://github.com/charliehzm/medharness/discussions/categories/q-a)
2. 看 [training/FAQ.md](../training/FAQ.md)
3. 提 Issue 用 `bug_report` 或 `feature_request` 模板
4. 微信群（README 里有邀请链接）

---

## 内测期专属反馈通道（D5 内测 5 人）

如你是 D5 内测人员：
- 实时反馈：直接发我（maintainer 微信）
- 卡住超过 5 分钟 → 截图 + 报错文本 → 反馈
- 我会 1 小时内修一版

谢谢你的耐心。
