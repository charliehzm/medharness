# Tasks · 20 任务 × 4 phase × 3-5 周

> Step 4 拆解输出。每任务 ≤ 5 文件 + 单 PR + 走 12 步 SOP。
> 命名：`T<N>-<slug>`，对应 sub-change 目录 `openspec/changes/feat-edge-tier-production-v0.5.0/T<N>-<slug>/`

---

## Phase 1 · 合规底层（week 1-2）⚠️ 关键路径

### T1 · phi-detector v3 真集成 Presidio
**Owner**：codex / **Reviewer**：Claude（异构）
**Spec**：[specs/T1-phi-detector-prod.spec.md](specs/T1-phi-detector-prod.spec.md)
**改动**：
- `mcp/phi-detector/server_v3.py` → 用 `presidio_analyzer.AnalyzerEngine`
- 加载 `mcp/phi-detector/recognizers/cn_*.py`（中文医疗 11 个）
- 加载 `mcp/phi-detector/fields.yml`（31 条）
- 6 上下文规则保留（Luhn / 占位符 / 日志时间戳 / 姓名邻近 / 60s 缓存 / CN-Bank）

**DoD**：
- [ ] `tests/red-team-drills/drill_phi_recall.py` 真跑 → recall ≥ 92%
- [ ] 误判率（FP） ≤ 15% on synthetic_phi_corpus.jsonl
- [ ] CI gate enforce
- [ ] 单测覆盖率 ≥ 80%（仅 mcp/phi-detector/）
- [ ] AUDIT_BUNDLE 生成

---

### T2 · desensitize → cryptography + FileKeyProvider
**Spec**：[specs/T2-desensitize-kms.spec.md](specs/T2-desensitize-kms.spec.md)
**改动**：
- `mcp/desensitize/server_v2.py` 真用 `cryptography.fernet`
- 新增 `mcp/desensitize/key_provider/`
  - `interface.py`（KeyProvider abstract）
  - `file_provider.py`（v0.5.0 实现）
  - `vault_provider.py.skel`（v1.0 占位）
  - `aliyun_kms.py.skel`（同）
  - `aws_kms.py.skel`（同）
- 反向映射表 ClickHouse schema

**DoD**：
- [ ] 加密 / 解密 roundtrip pass（合成数据）
- [ ] Key rotation 工作（新 key + 老数据可解）
- [ ] FileKeyProvider chmod 400 校验
- [ ] AES-256-GCM
- [ ] 单测 ≥ 80%

---

### T3 · model-router runtime gate
**Spec**：specs/T3-model-router-gate.spec.md
**改动**：
- `mcp/model-router/server_v2.py` 加 3 层校验
- 新增 `mcp/model-router/vendor_families.yml`
- 加 circuit breaker（连续 N 次拒同一 agent_role → SEV-2）
- 加 rate limiter（per agent_role）
- `MODEL_ALLOWLIST.json` 热加载

**DoD**：
- [ ] 异构性 runtime check：同家族 → 拒绝 + 落 audit
- [ ] allowlist 不命中 → 拒绝
- [ ] 数据分级越权 → 拒绝
- [ ] overhead < 5ms per call
- [ ] T5 drill 2 router bypass 验证通过

---

### T4 · audit-log WORM 3 层
**Spec**：specs/T4-audit-log-worm.spec.md
**改动**：
- `mcp/audit-log/server.py` 真集成 ClickHouse client
- ClickHouse schema：`_audit_log` MergeTree append-only
- 文件 chattr +a 脚本：`scripts/setup-worm.sh`
- 哈希链：每行 `prev_hash` / `current_hash`
- daily verify cron：`scripts/verify-hashchain.sh`

**DoD**：
- [ ] DELETE/UPDATE 在 _audit_log 上权限被拒
- [ ] 文件 chattr +a 设上后 rm 不掉
- [ ] 哈希链断 → daily verify 报警
- [ ] 6 个月 fixture 数据可重放（T6 drill 3 复用）

---

## Phase 2 · 红队 + 评估（week 2-3）

### T5 · drill 2 router bypass 实现
**改动**：
- `tests/red-team-drills/drill_router_bypass.py` 从 stub → 真实现
- 用例：直连境外 API 绕开 router / 同家族 model 通过 / 越权数据分级

**DoD**：
- [ ] 10+ 攻击用例
- [ ] 所有用例预期 → 阻断
- [ ] CI gate enforce

---

### T6 · drill 3 audit replay 实现
**改动**：
- `tests/red-team-drills/drill_audit_replay.py`
- 抽样既有 AUDIT_BUNDLE → 重新跑同模型 + 同 prompt → 对比 routing_decisions

**DoD**：
- [ ] 100% 重放成功率（temperature 容差内）
- [ ] 故意篡改哈希链 → 检测出
- [ ] CI gate enforce

---

### T7 · drill 4 prompt injection 实现
**改动**：
- `tests/red-team-drills/drill_injection.py`
- 模拟 RAG 中嵌入恶意指令 / 工具滥用 / 角色越权

**DoD**：
- [ ] 20+ 注入用例
- [ ] 阻断率 ≥ 95%
- [ ] CI gate enforce

---

### T8 · CI · 红队月度 cron + recall gate
**改动**：
- `.github/workflows/compliance.yml` 已存在 → 强化 gate
- 月度 schedule（每周一已有，确认 OK）
- recall 退化到 < 92% → CI fail + 通知 maintainer

**DoD**：
- [ ] 月度自动跑通
- [ ] 退化告警通过 Issue 自动开
- [ ] 历史 recall 趋势图（GitHub Actions artifact）

---

## Phase 3 · 部署编排（week 3-4）

### T9 · 8 MCP Dockerfile（非 root + multi-stage）
**改动**：
- `mcp/<name>/Dockerfile` × 8（每个 server 一份）
- base image：`python:3.11-slim`
- 非 root user `medharness:medharness`
- multi-stage：builder + runtime
- HEALTHCHECK 指令
- LABEL 含 version / sbom

**DoD**：
- [ ] 8 个 image 大小 < 500MB each
- [ ] `docker scan` 0 high vuln
- [ ] 非 root 跑通
- [ ] HEALTHCHECK 正确

---

### T10 · docker-compose.prod.yml + 网络隔离
**改动**：
- `deploy/docker-compose.prod.yml`
- network：`medharness_internal`（不暴露 host）+ `medharness_dmz`（仅 nginx）
- volume：`/data/medharness/*` host 挂载
- depends_on + healthcheck 链
- 资源 limit（mem / cpu）

**DoD**：
- [ ] `docker compose up` 后 8 服务全 healthy
- [ ] 服务间走 internal network（不通 host network）
- [ ] 重启后数据持久
- [ ] 资源 limit 合理（30 人公司用）

---

### T11 · TLS 工具 + nginx 反代
**改动**：
- `scripts/gen-tls.sh` → self-signed cert
- `deploy/nginx.conf` → 反代 8 MCP 暴露统一 HTTPS endpoint
- `install.sh --cert/--key` 支持 BYO cert
- 过期 30 天前告警

**DoD**：
- [ ] self-signed 生成可用
- [ ] BYO cert 路径可用
- [ ] 过期检测脚本工作
- [ ] HSTS / TLS 1.2+ only

---

### T12 · 备份 / 恢复 / 升级 / 卸载脚本
**改动**：
- `scripts/backup.sh` → ClickHouse + Qdrant + audit/ + keystore/ 全量 + 增量
- `scripts/restore.sh` → 反操作
- `scripts/upgrade.sh` → 从 v0.4.x → v0.5.0（下一版本用）
- `scripts/teardown.sh` → docker compose down + volume rm + image rm

**DoD**：
- [ ] 备份 + 恢复一遍数据无丢
- [ ] 卸载后 0 残留（image / volume / network）
- [ ] 升级路径（zero downtime 不强求）

---

## Phase 4 · 离线打包 + 文档（week 4-5）

### T13 · build-offline.sh（macOS + Linux）
**Spec**：[specs/T13-offline-build.spec.md](specs/T13-offline-build.spec.md)
**改动**：
- `scripts/build-offline.sh`
- buildx 多架构（linux/amd64 主，linux/arm64 可选）
- pip download → wheels/
- spaCy model 下载 → models/
- 产物：`dist/medharness-offline-v0.5.0-edge-<arch>.tar.gz`

**DoD**：
- [ ] macOS / Linux 都能跑
- [ ] tarball < 6 GB
- [ ] 可重复构建（同 commit 同产物）

---

### T14 · install.sh（无网目标机）
**Spec**：[specs/T14-install-script.spec.md](specs/T14-install-script.spec.md)
**改动**：
- `install.sh`：
  - guard：docker / docker-compose / 磁盘 / 端口
  - `docker load` 全部 image
  - 装 wheels 到容器内 venv（如需）
  - 启 compose
  - 等 healthy
- 支持 `--cert/--key` / `--data-dir` / `--port` flags

**DoD**：
- [ ] 在 Ubuntu 22.04 / CentOS Stream 9 / UOS 跑通
- [ ] 总耗时 ≤ 5 min（docker load 后）
- [ ] guards 完整（OS / docker version / 资源）

---

### T15 · verify.sh（装完自动验证）
**改动**：
- `verify.sh`：
  - 健康检查 8 MCP
  - 跑 dryrun_e2e_v2.sh（用 docker exec）
  - 跑 red-team drills 4/4
  - 验证 AUDIT_BUNDLE 上链
  - 生成 verify-report.html

**DoD**：
- [ ] verify 通过 → exit 0 + report
- [ ] verify 失败 → 明确指出哪一步 + 怎么修
- [ ] 总耗时 ≤ 8 min

---

### T16 · 镜像签名 + tarball 签名
**改动**：
- buildx 时 `cosign sign` 每个 image
- tarball 生成 SHA256SUMS + GPG 签
- install.sh 默认验签（可 `--skip-verify` 跳）

**DoD**：
- [ ] cosign verify 通过
- [ ] GPG verify 通过
- [ ] 签名失败 → install.sh 拒装（除非 --skip-verify）

---

### T17 · 运维 runbook
**改动**：
- `docs/runbooks/`
  - 00-day-0-install.md
  - 01-backup-restore.md
  - 02-upgrade.md
  - 03-incident-response.md
  - 04-audit-replay.md（4h 监管应对）
  - 05-tls-rotation.md
  - 06-kms-key-rotation.md
  - 07-add-new-skill.md
  - 08-troubleshooting-top10.md
  - 09-decommission.md

**DoD**：
- [ ] 每 runbook ≥ 500 字 + 命令清单
- [ ] 新人按步骤可完成（找 5 个内测人员实测）

---

### T18 · 监管审计应对演练
**改动**：
- `docs/runbooks/04-audit-replay.md` 详细版
- `scripts/audit-respond.sh`：4h 内产出完整 AUDIT_BUNDLE 包
- 演练剧本：监管说 "我要回放 2026-03 那个 PR 的所有 LLM 调用"

**DoD**：
- [ ] 实测 4h 内完成（用 v0.1 archived bundles 模拟）
- [ ] 输出含：完整 prompt history / model versions / routing decisions / 哈希链

---

### T19 · 离线包 e2e 验证（Lima / qemu 模拟空气墙）
**改动**：
- `tests/offline-e2e/`
  - `lima.yml` / `qemu-cmd.sh` 起 Ubuntu 22.04 VM（无外网）
  - 自动 copy tarball + 跑 install + 跑 verify
- CI workflow：`offline-e2e.yml`（push tag 时触发）

**DoD**：
- [ ] CI 自动跑通离线 e2e
- [ ] 3 个 OS 矩阵：Ubuntu 22 / CentOS Stream 9 / Debian 12

---

### T20 · v0.5.0-edge release + 配套博客
**改动**：
- CHANGELOG.md
- 发布 release notes
- 博客 draft：《MedHarness v0.5.0-edge · 第一个生产部署包》
- 公众号 / 知乎 / V2EX 发布文案
- 更新 README + docs/roadmap 标 M3 已达

**DoD**：
- [ ] git tag v0.5.0-edge
- [ ] GitHub Release Published（不 Draft）
- [ ] 博客 draft 给 maintainer review
- [ ] 0 P0 / P1 bug 未修

---

## 依赖图

```
T1 ───→ T5
T2 ───→ T17 (kms rotation runbook)
T3 ───→ T5 (drill 2 需要 router gate)
T4 ───→ T6 (drill 3 需要 audit log)

T1-T4 并行（不同模块）
T5-T7 并行（drill 之间独立）
T8 串行（在 T5-T7 后）

T9 ───→ T10 → T11 → T12

T13 ───→ T14 → T15
T16 (signing) 并行 T13-T15
T17-T18 并行（文档）
T19 串行（在 T13-T16 之后）
T20 串行（最末）
```

---

## 并行建议（如 codex 多分支）

| Week | 同时进行 |
|---|---|
| W1 | T1 + T2（不同模块） |
| W2 | T3 + T4（不同模块） |
| W3 | T5 + T6 + T7（drill 互独立） |
| W4 | T9-T12 串行 + T16 并行 |
| W5 | T13-T15 串行 + T17-T18 并行 |
| W5+ | T19 → T20 |

---

## 总工时估算

| Phase | 任务 | 工时 |
|---|---|---|
| 1 | T1-T4 | ~80h（含测试） |
| 2 | T5-T8 | ~40h |
| 3 | T9-T12 | ~50h |
| 4 | T13-T20 | ~70h |
| **合计** | | **~240h** |

- 单 codex 全职：3-4 周
- codex + 你 review + Compliance Officer 兼任：4-5 周
- 含意外 / 重写 / 红队修复：5-6 周

---

## 风险监控（每周看一次）

| 风险 | 监控点 |
|---|---|
| 进度滞后 | tasks DoD 实际完成 vs 计划 |
| 质量打折扣 | recall / FP / 重放率 三指标 |
| PHI 漏出 | red-team drill + PR 文件改动审计 |
| 体积失控 | tarball size / image size |
| 测试覆盖率退化 | pytest coverage --fail-under=80 |

未达 → 回归 maintainer 评估是否启用 fallback（推迟 / 砍范围）。
