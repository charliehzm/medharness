# 贡献指南 · Contributing to MedHarness

> 谢谢你愿意为医疗 AI Coding 体系出力。先读这份，再开 PR。
> 这是一个有合规红线的项目，比一般开源项目多一道审查 — 但流程会很清晰。

---

## TL;DR · 30 秒版

1. Fork → 改 → 写测试 → 跑 `bash dryrun_e2e_v2.sh`
2. 提 PR 时勾选 PR 模板的"合规自检"
3. 涉及 PHI 字段 / 模型路由 / 审计变更 → 必须 @合规 owner

---

## 我能贡献什么？

### ✅ 欢迎的贡献

- **新 Skill**：写在 `.claude/skills/<name>/SKILL.md`，参考现有 21 个的格式
- **新 Sub-agent**：写在 `.claude/sub_agents/<name>.md`
- **MCP server 完善**：`mcp/` 下 8 个 server 的 v2 实现
- **Hook 规则优化**：`scripts/hooks/` 的 9 个脚本
- **fields.yml 新字段**：中文医疗字段（中医术语、医院 MRN 规则）
- **培训材料**：`training/` 下补充课件 / 案例
- **文档修订**：错别字 / 链接失效 / 翻译
- **示例 change**：`examples/` 下加新场景（药品不良反应上报 / 影像系统对接等）

### ❌ 不欢迎的贡献

- 关闭 / 绕过 Hook 的 PR
- 把 PHI 检测规则放宽（除非有红队演练证明 false positive）
- 引入境外公共 LLM 直连（不经 model-router）
- 改 License 收紧（已永久承诺）

---

## 第一次贡献流程

### 1. 准备
```bash
git clone https://github.com/<you>/medharness.git
cd medharness
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install
```

### 2. 选 issue
- 看 `good first issue` label 入门
- 大改动先开 Discussion 讨论再写代码（避免徒劳）

### 3. 改 + 测
- 改一项就跑 `pytest tests/integration/test_<area>.py`
- 整体合规跑：`bash tests/red-team-drills/run_all.sh`

### 4. 跑 dryrun
```bash
bash dryrun_e2e_v2.sh
```
出 `AUDIT_BUNDLE.tar.gz` 表示通过。

### 5. 提 PR
- 标题：`feat(<scope>): <短描述>` / `fix(...)` / `docs(...)` / `chore(...)`
- 体内 fill 完 PR 模板的"合规自检 5 问"

### 6. 等 review
- 普通 PR：2 maintainer review（Reviewer-Agent + 人工）
- 涉合规 PR：**额外** Compliance Officer review
- SLA：4 天首次反馈、14 天合并或闭

---

## 代码风格

| 语言 | 风格 |
|---|---|
| Python | black 23+ / ruff E,F,I / mypy --strict | 
| Shell | shellcheck 通过 |
| Markdown | 行宽 100，标题层级 ≤ 4 |
| 中文文档 | 标题中文，code/path 英文 |

`.pre-commit-config.yaml` 已配，install 后自动跑。

---

## 合规自检 5 问（PR 必填）

提 PR 前，自己回答：

1. 本 PR **是否会让 PHI 进入 prompt** 路径？如是，是否前置 `phi-desensitize`？
2. 本 PR **是否新增 LLM 调用**？如是，是否走 `mcp-model-router`？
3. 本 PR **是否绕过任何 Hook**？如是，理由 + 双委员会签字 issue 链接？
4. 本 PR **是否处理真实生产数据**？如是，是否 100% 合成 + 指纹核验？
5. 本 PR **是否影响审计血缘**？如是，AUDIT_BUNDLE schema 是否更新？

任一回答模糊 → review 会被打回。

---

## Skill Owner 制

每个 Skill 有一个 owner。Owner 职责：
- 季度审计 description / trigger 命中率
- 维护 references / templates / examples
- 跟踪失败案例

成为 Skill Owner：
- 拿 5 个相关 PR merged
- 在 Discussions 申请，maintainer 批准

---

## 重大变更（RFC 流程）

如果你想：
- 改 6 层架构
- 改 12 步 SOP
- 改 License 范围
- 新增红线规则

→ 先开 RFC：`openspec/changes/rfc-<name>/proposal.md`，社区讨论 14 天，maintainer + 合规委双确认后实施。

---

## 沟通渠道

- **GitHub Issues**：bug / 功能请求
- **GitHub Discussions**：问题 / 想法 / 案例分享
- **Compliance concerns**：`security@medharness.io`（不公开）
- **Community Call**：月度，Discussions 公告
- **微信群（中文）**：用户群 / 贡献者群（加我 wx：见 maintainer 邮箱）

---

## 行为准则

遵循 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)（Contributor Covenant 2.1）。

简单说：对人友善，对代码严苛。

---

## License

提交 PR 即表示你同意：
- 代码贡献按 [Apache 2.0](LICENSE) 授权
- 文档贡献按 [CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0) 授权
- 你拥有所提交内容的版权 / 已获授权

---

## 一句话感谢

> 你的第一个 PR，无论多小，我们都会真诚感谢。
> 因为开源项目的命运，就是被这些 PR 一点一点改变的。
