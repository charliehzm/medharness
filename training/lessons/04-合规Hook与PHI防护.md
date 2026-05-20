# 课件 04 · 合规 Hook 与 PHI 防护

> 时长：60 分钟
> 受众：所有人，特别是 Compliance Officer / 法务
> 前置：课件 01-03

---

## 学习目标

- 知道 9 个 Hook 各自在拦什么
- 理解 phi-detector v3 的 6 条规则优化
- 能复盘一次 false positive 误判事件

---

## 1. Hook 是什么（5 min）

Hook = Claude Code 在固定生命周期事件触发的脚本。
`.claude/settings.json` 声明哪个事件挂哪个 hook。

事件类型（常用）：
- `SessionStart` · 会话起步
- `UserPromptSubmit` · 用户提交 prompt 前
- `PreToolUse` · Tool 调用前
- `PostToolUse` · Tool 调用后
- `Stop` · 会话结束

Hook 用法：**warn 默认**（不阻断，写日志），企业用户可改 **block**。

---

## 2. 9 个 Hook（20 min）

| Hook | 事件 | 干啥 |
|---|---|---|
| `session_banner.py` / `v2` | SessionStart | 打 banner（项目信息 / 当前 change / 红线提示） |
| `compliance_tag_check.py` / `v2` | PreToolUse | 检查 COMPLIANCE_TAG.md 是否三方签字 |
| `phi_detect.py` / `v2` / `v3` | UserPromptSubmit | 扫 prompt 含 PHI 即阻断 / warn |
| `model_router_gate.py` / `v2` | PreToolUse | 检查 LLM 调用是否在 allowlist |
| `audit_log_append.py` | PostToolUse | 落日志到 mcp-audit-log |
| `skill_invocations_log.py` | PostToolUse | 记录 Skill 触发命中 / miss |
| `stop_summary.py` | Stop | 会话结束摘要 + 异常告警 |

`v2` / `v3` 是 evolution — 旧版保留兼容，**默认用最新版**。

---

## 3. phi-detector v1 → v3 演化（15 min · **重点**）

### v1 误判率 66%（开发者 1 周后关掉了）

| 误判类型 | 例子 | v1 行为 |
|---|---|---|
| 日志时间戳 | `2026-05-20 14:00:00` | 当 cn_id 阻断 |
| 占位符 | `<phi>` / `ID-123` | 当 cn_id 阻断 |
| 测试身份证 | `110101199001011234`（公开占位） | 当 cn_id 阻断 |
| 银行卡号 | 16-19 位数字 | 误识别为 PHI |

### v3 的 6 条规则（误判率 → < 15%）

1. **Luhn 算法严格校验**：cn_id / 银行卡号必过 Luhn check
2. **占位符 suppress 列表**：已知占位 + `<phi>` / `${phi}` / `ID-XXX` 等
3. **日志时间戳上下文规则**：前后有 log level 关键词（INFO / ERROR / DEBUG）→ 不识别
4. **姓名邻近上下文**：前后含"医生 / 患者 / 病人"→ 加权识别；含"员工 / 用户 / Co-Author"→ 降权
5. **60s session 缓存**：同 prompt 60s 内重复扫，直接复用结果
6. **CN-Bank 严格化**：要求 16-19 位 + 银行 BIN 前缀 + Luhn

详 `mcp/phi-detector/server_v3.py`。

---

## 4. False Positive 复盘流程（10 min · 实操）

当你看到 hook 误判：

### Step 1 · 收集
```
【输入文本】（脱敏）
【期望】不阻断
【实际】阻断为 cn_id
【上下文】哪里触发的
```

### Step 2 · 提交
在 [Discussions #4](https://github.com/charliehzm/medharness/discussions/4) 按格式回帖。

### Step 3 · 加入 fixtures
我们会加到 `tests/red-team-drills/fixtures/phi_corpus.jsonl`。

### Step 4 · 月度红队复测
```bash
bash tests/red-team-drills/run_all.sh
python tests/red-team-drills/check_recall.py --min 0.92
```

### Step 5 · 规则迭代
如证实是规则问题 → next release 修。

---

## 5. False Negative（漏报）远比 false positive 危险（5 min）

| 类型 | 后果 | 监管视角 |
|---|---|---|
| False positive（误判 / 阻断不该阻断的） | 开发者抱怨 | 不算违规 |
| **False negative（漏报 / 真 PHI 没拦） | PHI 泄漏 → 监管罚 + 客户信任崩盘** | 重大违规 |

**红队 drill 1 的 recall ≥ 92%** 就是为这个：我们宁可多误判，也不漏报。

---

## 6. 紧急情况：发现真实 PHI 泄漏

立即：
1. 暂停所有 LLM 调用
2. 走 [SECURITY.md](../../SECURITY.md) 私密通道：`security@medharness.io`
3. **不在 public Issue 公开披露**
4. maintainer + 律师 24h 内响应

详 SECURITY.md `披露流程`。

---

## 7. 课后作业

1. 跑一遍 `bash tests/red-team-drills/run_all.sh`
2. 看 `tests/red-team-drills/output/recall.json`，记下当前 recall 数字
3. 想一个你工作场景的 false positive 案例，在 Discussions #4 提
4. 完成 [05-Memory系统使用.md](05-Memory系统使用.md)

---

## 自检

- [ ] 我能说出 9 个 Hook 各自在拦什么
- [ ] 我背得出 v3 的 6 条规则
- [ ] 我知道 false negative 比 false positive 危险
- [ ] 遇到 PHI 真泄漏，我知道走 SECURITY.md 不公开
