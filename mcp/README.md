# MCP Servers · 医疗合规层

> 这一层是 L5 合规层的运行时执行点。所有合规 Hook 与合规 Skill 通过这些 MCP server 与系统对话。

## 三件套（M2 必须）

| 目录 | 用途 | Hook 触发 | 上线阶段 |
|---|---|---|---|
| [phi-detector/](phi-detector/) | 实时 PHI / PII 检测 | `UserPromptSubmit`、CI | M2 |
| [desensitize/](desensitize/) | 脱敏 + 反向映射表管理 | `phi-desensitize` Skill | M2 |
| [model-router/](model-router/) | 按 MODEL_ALLOWLIST 路由模型 | `PreToolUse`、所有 LLM 调用 | M2 |

## 设计共识

1. **每个 MCP server 都是独立进程**：失败隔离、可单独升级、可独立审计。
2. **接口契约用 JSON Schema 锁死**：见每个目录的 `schema/` 子目录。
3. **所有调用必须落审计**：每个 server 自己写 `.audit/mcp_<name>.jsonl`，与外层 `mcp-audit-log` 双备份。
4. **零状态优先 / 必要状态本地**：detector / router 是无状态；desensitize 的反向映射表落本地加密文件（不上云）。
5. **失败模式**：网络/依赖失败 → fail-closed（拒绝放行），不允许 fail-open。

## M2 上线顺序
1. phi-detector（先有就能堵住 prompt 出血点）
2. model-router（接着把 LLM 调用强制路由起来）
3. desensitize（与 phi-desensitize Skill 配套）

## 后续 MCP（M3+）
- mcp-audit-log（M3，WORM 后端）
- mcp-internal-kb（M3）
- mcp-vector-db（M4）
- mcp-ci-trigger（M4）
- mcp-pm-bridge（M5）
