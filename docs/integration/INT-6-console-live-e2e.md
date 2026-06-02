# INT-6 · Console live-mode E2E 冒烟与截图

> 目标：证明自建 Console（`web/`）能**端到端**渲染在**真实 A0 BFF** 之上（而非 INT-1 的进程内
> mock），且全程使用合成数据、0-PHI。这是 INT-5a（live-A0 后端冒烟）之上的 UI 层验证。

## 前置

- Docker + Docker Compose。
- bun（前端按 `vendor/new-api` 约定用 bun；仓库有 `web/bun.lock`）。
- `medharness/mcp-a0-api:int5` 镜像（INT-4/5 已构建；缺失时 `bash scripts/docker-build.sh a0-api` 后改 tag，或直接跑 INT-5 流程构建）。

## 复现步骤

1. **拉起 live 后端**（真实 ClickHouse + 真实 A0，合成数据）：

   ```bash
   bash scripts/int5_console_smoke.sh --keep
   ```

   该脚本：建专用 network → 起 ClickHouse(:18123) → 用 `scripts/dev_seed_audit.py`
   注入 24 行合成、哈希链 `_audit_log` → 起 A0(:19000，连真实 CH) → 断言
   `/api/v1/{posture,traffic,events,cost,channels,upstreams}` 全部 200 且非空、audit
   按真实 ref 可查、并做 0-PHI spot check（载荷中无 `email`/`phone`/`raw_text`/`prompt`
   标记）。`--keep` 保留 CH:18123 + A0:19000 供前端连调。

2. **前端 live 模式**（vite dev 代理 `/api/v1` → `127.0.0.1:19000`，见 `web/vite.config.ts`）：

   ```bash
   cd web
   bun install
   VITE_API_MODE=live bun run dev
   ```

   `VITE_API_MODE=live` 让 `web/src/api/client.ts` 走真实 fetch（默认 `mock`）。
   打开 dev server 输出的 URL（默认 http://localhost:5173）。

3. **逐屏渲染 + 截图**：依次进入「总览 / 流量监控 / 审计与报表 / 用量与成本 / 接入 /
   策略 / 系统」，确认右上「全程 0 PHI」常驻、数据来自 :19000，逐屏截图。

4. **拆栈**：

   ```bash
   docker rm -f mh-int5-ch mh-int5-a0 && docker network rm medharness-int5
   ```

   （或直接不带 `--keep` 重跑冒烟，trap 会自动清理。）

## 0-PHI 不变量

- 数据来源是合成 seeder（`scripts/dev_seed_audit.py`），**不触碰任何真实 provider / PHI / `.env`**。
- A0 BFF 按字段白名单序列化；前端 `assertNoPhi` 兜底（cn_id / cn_phone / email 正则）。
- 冒烟脚本的 0-PHI spot check 对聚合载荷断言无 PHI 标记。

## 已采集截图（live A0 渲染，均带「全程 0 PHI」）

覆盖 Console 三大价值轴：**安全 / 划算 / 治理**。

| 屏 | 文件 | 内容 |
|---|---|---|
| 流量监控（安全） | [console-live-traffic.png](console-live-traffic.png) | 「调用去向与处置」桑基流：Dify RAG / ComfyUI / Codex → 安全检查（隐私扫描+脱敏+准入）→ 私有模型 / 境外模型（已脱敏 12 · ×阻断 3）；下方双色实时事件流（合规绿 / 安全紫），含「脱敏后路由 qwen-max · routing#a1b2」「检索内容含可疑指令→隔离」。 |
| 用量与成本（划算） | [console-live-cost.png](console-live-cost.png) | 成本卡片（月总 / 月省 / 命中率）、成本健康度仪表、按通道 / 按模型成本构成、智能省钱建议、省钱效果。 |
| 系统（治理/运维） | [console-live-system.png](console-live-system.png) | 规划中占位屏（`built:false`）：部署健康、备份与升级入口预留位；体现诚实边界。 |

> 这三屏为 live-A0 代表性采集，跨「安全/划算/治理」三轴。逐屏双角色（研发负责人 /
> 系统管理员）视觉核对已在单独一轮完成（见任务「浏览器渲染逐屏双角色核对」）；按上面
> 步骤 1–3 可随时重生成任意屏。

## 结论

**INT-6 PASS** — 自建 Console 在真实 A0 BFF 上的 live 渲染端到端打通，可复现，全程 0-PHI。
