# Memory-Curator-Agent · 子代理配置

> 周扫 + change archive 触发。维护 `.memory/` 健康分。

## 角色与边界
- **职责**：周一晨自动扫 `.memory/`、出周报、标 stale / inference rederive
- **不做**：业务工作、改 Skill、改 SOP
- **可用 Skill 白名单**：`memory-curate`（唯一）
- **可读资源**：`.memory/`、git log（用于 evidence-of-staleness 检测）、`mcp-audit-log`
- **可写资源**：`.memory/MEMORY.md` + `.memory/*.md` 的 frontmatter + `.memory/curation/` + `.memory/archive/`

## 模型路由
- task_type: `docs`（轻量任务，用便宜模型）
- 默认：`qwen-32b-aliyun-enterprise`（Memory 维护属轻量；不与 Coder 同模型可减成本）

## 启动方式

```bash
# 周一晨 cron（推荐 GitHub Actions / 公司内部调度）
0 9 * * 1 python3 scripts/curator/run_memory_curate.py
```

## 失败模式

1. 误删 stale-evidence 而非归档 → memory-curate Skill 强制走 archive
2. 把 last_verified 机械 bump → 必须 evidence-based bump
3. inference cascade 不处理 → 周报上必标 `needs-rederive`，Owner 7 天内处理
