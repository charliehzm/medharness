# 06 · 自检 protocol

> 在每个会话 / 每条响应 / 每次 PR 之前，跑这份 protocol。
> 1 分钟，避免 90% 的灾难。

---

## 1. 三层自检

```
┌──────────────────────────────┐
│ L1 · 响应级（每条 ≤ 10s）     │ ← 每条用户响应前
├──────────────────────────────┤
│ L2 · 会话级（每次 30s）       │ ← 每次会话开始 / 结束
├──────────────────────────────┤
│ L3 · 改动级（每次 PR ≤ 60s）  │ ← 每个 commit 前
└──────────────────────────────┘
```

---

## 2. L1 · 响应级自检（10 秒 · 每条响应前）

回答用户前，问自己：

| # | 问 | 通过 |
|---|---|---|
| 1 | 我定位了阶段（DEV / TEST / OPS）吗？ | yes |
| 2 | 我引用文件用 `path:line` 格式吗？ | yes |
| 3 | 我触及 PHI / 模型 / 审计 时显式合规自检了吗？ | n/a 或 yes |
| 4 | 我没凭空发明项目级新决策吧？ | yes |
| 5 | 我没绕过 SOP 直接写代码吧？ | yes |
| 6 | 我没改 LICENSE 收紧吧？ | yes |
| 7 | 我没公开发声 / 签合同吧？ | yes |

任一 no → 重写响应。

---

## 3. L2 · 会话级自检

### 3.1 会话开始（30 秒）

```bash
# 1. 项目脉搏
git log --oneline -20
git status

# 2. 路线图位置
grep "当前月" .memory/项目档案.md

# 3. 未完成事项
cat HANDOFF/CURRENT_TODOS.md 2>/dev/null

# 4. inbox（如有）
ls HANDOFF/inbox/ 2>/dev/null
```

### 3.2 会话结束（30 秒）

```
[ ] CHANGELOG.md 已更新（如有 release-worthy 改动）
[ ] HANDOFF/CURRENT_TODOS.md 已更新
[ ] 写了 ≤ 5 行交接 note（给下个会话）
[ ] 改动已 commit（如 maintainer 授权）
[ ] 自检 §4 (R1-R5 红线) 通过
```

---

## 4. R1-R5 红线自检（每次改动）

| 红线 | 自检问 | 通过条件 |
|---|---|---|
| R1 PHI 不裸入 prompt | 我改的代码会让真实 PHI 进入 LLM 入参吗？ | 否 / 已前置 `phi-desensitize` |
| R2 模型按 allowlist | 我新增的 LLM 调用走 `mcp-model-router` 了吗？ | 是 |
| R3 审计全量 | 我新增的 tool / Skill / 模型调用落 `mcp-audit-log` 了吗？ | 是 |
| R4 测试数据合规 | 我新增的测试数据 100% 合成 + 指纹核验吗？ | 是 / 用现成 `test-data-generation` |
| R5 License 永久 | 我没改 LICENSE / LICENSE-CC-BY-SA-4.0 吧？ | 是（除非走双委员会） |

任一不通过 → **停手**，写 incident note 给 maintainer。

---

## 5. L3 · 改动级自检（每次 PR ≤ 60 秒）

### 5.1 SOP 自检

```
[ ] 这是 micro 通道（5 步）还是 12 步主通道？
[ ] 关联了 openspec/changes/<id>/ 吗？
[ ] proposal.md / tasks.md / specs/ / COMPLIANCE_TAG.md 齐了吗？
[ ] Step 0 合规预检三方签字了吗？（micro 通道：1 方）
```

### 5.2 测试自检

```bash
ruff check <touched files>
pytest tests/integration/test_<area>.py
bash dryrun_e2e_v2.sh                    # 如改动 SOP / Skill / Hook
bash tests/red-team-drills/run_all.sh    # 如改动合规规则
```

### 5.3 文档自检

```
[ ] README.md 改了吗？（如适用）
[ ] CHANGELOG.md 加条目了吗？
[ ] CLAUDE.md 改了吗？（如红线变化）
[ ] training/ 改了吗？（如 SOP 变化）
[ ] docs/troubleshooting.md 改了吗？（如新坑发现）
```

### 5.4 PR 描述自检

PR 描述模板（[.github/pull_request_template.md](../.github/pull_request_template.md)）：
- [ ] 概要 1-2 句
- [ ] 类型（feat / fix / docs / refactor / test / chore / compliance）
- [ ] 涉及范围（Skill / Sub-agent / MCP / Hook / SOP / fields.yml / 培训）
- [ ] 合规自检 5 问（必填）
- [ ] 测试通过截图 / 日志
- [ ] 文档更新对照

---

## 6. 高危操作前的"暂停 3 秒"

下列操作 → 暂停 3 秒，问"真的要做吗"：

| 操作 | 暂停理由 |
|---|---|
| 删任何文件 | 可能是 in-progress 工作 |
| 改 .claude/settings.json | 影响所有会话 |
| 改 LICENSE | 永久承诺 |
| 改 CLAUDE.md §1 红线 | 双委员会签字 |
| 改 phi-detector / desensitize 规则 | 漏率回升风险 |
| 改 model-router allowlist | 合规边界 |
| `git push --force` | 不可逆 |
| `git reset --hard` | 不可逆 |
| 接外部服务（云 KMS / WORM 后端） | 决策权问题 |

暂停后：
- 如确定 → 显式说"我准备做 X，确定？" 等 maintainer 确认
- 如不确定 → 升级（标 🚨 / ❓UNCERTAIN）

---

## 7. 自检失败后的复盘

如果你（AI）做错了一件事被 maintainer 指出：

1. **不辩解** — 别说"我以为是为了 ..."
2. **记录** — 把这条错误加到 [HANDOFF.md §6 7 个坑](../HANDOFF.md#6-7-个最容易踩的坑前任血泪)
3. **修复** — 不只是修这次的 bug，是问"系统性怎么避"
4. **传承** — 加到本 protocol 的 R1-R5 / §6 / §8 让下个会话避

错误一次是教训，重复犯是失职。

---

## 8. 触发红线 / 决策变更时的 emoji 标记

在响应里显式打：

| Emoji | 含义 | 后续 |
|---|---|---|
| 🚨 RED-LINE | 触及 R1-R5 | 停手 + maintainer 拍板 |
| 🚨 LEGAL | 涉法律 / 合规边界 | 律师介入 |
| 🎙️ COMMS | 涉公开发声 | maintainer 决定 |
| 🤝 PARTNER | 涉外部合作 | maintainer 决定 |
| 💰 COMMERCIAL | 涉商业谈判 | maintainer 决定 |
| 🧭 STRATEGY | 决策权超过项目级改动 | RFC 流程 |
| ❓ UNCERTAIN | 不确定 | 默认停手等人 |
| 🟢 SAFE | 我已自检 R1-R5 通过 | 可推进 |

---

## 9. 一份"今天的工作"模板（每个会话开始你给 maintainer）

```markdown
## 今日状态报告（2026-MM-DD）

**阶段**：M? · DEV / TEST / OPS
**仓库脉搏**：git log -3 简要

**昨天 / 上次会话完成**：
- ...

**今天准备做**：
1. ...
2. ...
3. ...

**阻塞 / 升级**：
- 🟢 SAFE：N/A
- ❓ UNCERTAIN：...

**自检**：
- R1-R5 红线通过 / N/A
- SOP 关联 change：openspec/changes/...

我开工？
```

---

## 10. 一句话

> 自检不是仪式。
> 是让"医疗 AI Coding"项目在 6 年后审计依然可重放的**护城河**。
>
> 慢 1 分钟，省 1 个月。
