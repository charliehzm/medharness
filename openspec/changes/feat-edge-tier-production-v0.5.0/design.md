# Design · 6 条架构决策（ADR）

> 本 change 内会用到的关键架构决策。**等价于 ADR**，每条都给"考虑过的替代 + 否决理由"。
> 决策一旦确认 → 锁定到 [HANDOFF/05-decisions-log](私有备份) D11+。

---

## ADR-01 · PHI 检测 backend：Presidio + 31 fields.yml

### 决策
用 Microsoft Presidio 的 `AnalyzerEngine` 作为底层，把 31 fields.yml 翻译为 Custom Recognizer 注入。

### 替代
- A) 自研 regex + ML 流水线 → 维护成本高，召回率打折
- B) Amazon Comprehend Medical / 阿里 NLP → 公共云依赖、跨境合规问题
- C) 直接用 Presidio default → 中文医疗 recall 不够

### 否决理由
A 工作量太大；B 数据出境；C 召回率不够。
我们用 C + 加 31 fields.yml 弥补 + 配 6 上下文规则提精度。

### 实施约束
- recall ≥ 92% on `synthetic_phi_corpus.jsonl`
- 误判率（FP） ≤ 15%
- 推理时延 < 100ms / per 1K chars（CPU）
- spaCy 模型用 `zh_core_web_sm`（85MB · 离线包内置）

---

## ADR-02 · 脱敏 KMS 抽象：先文件 keystore，BYO 接口预留

### 决策
`mcp-desensitize` 暴露 `KeyProvider` 抽象接口。
v0.5.0 实现 `FileKeyProvider`（key 文件存本地 + chmod 400）。
v1.0 起补 `VaultKeyProvider` / `AliyunKMSProvider` / `AWSKMSProvider`。

### 替代
- A) 直接集成 Vault → 客户没装 Vault 时部署不动
- B) 用 docker secret → docker swarm 才有，我们用 compose
- C) 不抽象 · 写死 cryptography.fernet → v1.0 升级时改动大

### 否决理由
A 客户无 Vault；B 我们不用 swarm；C 后续升级成本高。
抽象成本低，先用 File 实现，接口为云 KMS 留好。

### 实施约束
- KeyProvider 接口：`get_key(key_id) -> bytes` / `rotate(key_id) -> bytes` / `list_keys() -> [key_id]`
- 文件 keystore 路径：`/data/medharness/keystore/*.key`（host 卷）
- 默认 AES-256-GCM
- 反向映射表存 ClickHouse `_phi_lookup` 表，仅受控环境查询

---

## ADR-03 · 审计日志 WORM：ClickHouse + chattr +a + 哈希链 3 层

### 决策
v0.5.0 用 3 层防篡改而不依赖 OSS Object Lock：

1. **ClickHouse `_audit_log` 表**：MergeTree 引擎 + append-only DDL（无 ALTER UPDATE/DELETE 权限）
2. **Filesystem chattr +a**：底层 `/data/medharness/audit/*.parquet` 设 append-only 标志
3. **哈希链**：每行 audit 含 `prev_hash` + `current_hash`，断链 = 篡改

### 替代
- A) 直接 OSS Object Lock → 客户没买 OSS / 内网无对象存储
- B) 区块链上链 → 过度工程 + 监管不必要
- C) 简单 append-only 文件 → 单一防线，可被 root 改

### 否决理由
A 客户场景受限；B 杀鸡用牛刀；C 防线太薄。
3 层组合 + 客户可定期把哈希头 anchor 到第三方公证（v1.0 选项）。

### 实施约束
- 哈希算法：SHA-256
- 链头 anchor 到 `AUDIT_BUNDLE.tar.gz` 的 `hashchain.txt`
- 每天凌晨自动 verify 链完整性（cron + script）
- 链断 → 立即 SEV-1 报警

### T4 codex Q&A 落档（2026-05-24）

| # | 问题 | 答 |
|---|---|---|
| Q1 | clickhouse-driver vs clickhouse-connect 作为 canonical client | **clickhouse-connect** · ClickHouse 官方维护跟 24.x 同步 · HTTP 协议比 TCP native 9000 端口部署更友好（容器/反代/SaaS）· 5000 rows/sec 单连接远高于 1000 rows/sec SLO |
| Q2 | 哈希链公式 + row_id / timestamp 是否进 hash | **`sha256(canonical_json(event_with_row_id) + "\|" + prev_hash)`** · `\|` 分隔符防 length-extension 边界歧义 · row_id 作为 event 字段进 canonical（防行重排攻击）· timestamp 已在 canonical 不重复 |
| Q3 | ClickHouse 恢复后 fallback 回灌时链头怎么续 | **原链续 + PID lock + 恢复期顺序 backfill** · fallback 期 writer 内存里 `_last_hash` 继续 advance，每条 JSONL 写完整 prev/current hash → fallback 文件本身是有效链段 · 恢复时 daemon 进入 BACKFILL state 暂停新写入 → 按 ts 顺序 backfill → 完成后恢复 · bridge record 留 v0.5.1 plan B |
| Q4 | drill 3 audit replay 只验 hash 链，还是还要语义重放对比确定性输出 | **T4.9 只做 hash 链验证 + 篡改检测** · 6 个月 synthetic fixture · 故意篡改 1 行 → 检测 · 语义重放（重跑 prompt + temperature 容差对比）工程量翻倍，推迟 T6/v0.6+ 单独 RFC |
| Q5 | `_audit_log` 的 row_id 谁生成（writer 还是 ClickHouse） | **writer 端生成** · hash chain 要求写入前知道 row_id（ClickHouse 端生成则 chain 算不了）· v0.5.0 单实例 SELECT MAX + 内存 counter 够用 · 多 writer 升级路径用 `(writer_id, local_counter)` 元组（v1.0） |
| Q6 | setup-worm.sh chattr +a 只管 `_audit_log` 还是连 export/backup 一起管 | **三目录全管** · `_audit_log/` + `audit-export/` + `audit-backup/` · WORM 是全链路防篡改：攻击者可能改导出副本或备份骗审计员 → 全部 chattr +a · macOS skip + lsattr 验证存在性 + warning · Linux 实跑 chattr +a |

### T4 实施约束（codex Q&A 后补充）
- ClickHouse client：`clickhouse-connect`（HTTP 协议）
- 哈希公式：`sha256(canonical_json(event_with_row_id) + "|" + prev_hash)`
- Fallback 路径：`/data/medharness/audit/audit-fallback-<ts>.jsonl` + 单进程 PID lock
- Row ID：writer 端单调 counter（启动时 `SELECT MAX(row_id)` 初始化）
- WORM 目录：`_audit_log/` + `audit-export/` + `audit-backup/` 三目录独立 chattr +a
- CI 策略：unit tests（hashchain 纯函数 + writer mock）默认进 pytest · integration tests 标 `@pytest.mark.clickhouse` 默认 skip · `--full` 或本地手动跑

---

## ADR-04 · model-router 异构性 runtime check

### 决策
`mcp-model-router` 在路由前做 3 层校验：
1. 模型是否在当前 change 的 `MODEL_ALLOWLIST.json` 内
2. 调用者身份（agent_role）+ 目标模型的 vendor_family 是否触发异构性规则
3. 数据分级（来自 `COMPLIANCE_TAG.md`）是否允许目标模型

### 替代
- A) 仅 description 层提示（v0.1 现状） → 无强制力
- B) Hook 层拦 → Hook 是 best-effort，可被绕
- C) 业务代码自检 → 工程师会忘

### 否决理由
A/B/C 都依赖人，runtime gate 在 router 层是单点强制。
"自证清白"问题（v2.0 教训）必须用 runtime 不可绕的方式解。

### 实施约束
- 失败模式：`drop`（直接拒绝，不 fallback）+ 落 audit
- 容错：连续 N 次拒绝同一 agent_role → 升级到 SEV-2
- 性能：< 5ms overhead per call（含 PHI desensitized marker 检查，**不**做 inline subprocess scan）
- 配置：`MODEL_ALLOWLIST.json` 热加载（不重启 router）

### T3 codex Q&A 落档（2026-05-22）

| # | 问题 | 答 |
|---|---|---|
| Q1 | allowlist schema list-based vs task_type map-based | **list-based** · 每个 model entry 含 vendor_family / allowed_agent_roles / allowed_data_levels / rate_limit_qps · 异构性放 heterogeneity.py，allowlist 不重复表达 |
| Q2 | circuit breaker reject threshold（3 / 5 / configurable） | **configurable · default 5** · 5 是业界 transient 容错平衡点 |
| Q3 | T3.6 是否保留 PHI subprocess scan | **不在 router 内联** · request 必含 `metadata.desensitized: true` 标记 · 缺失 → fail-closed reject "must route through mcp-desensitize first" · subprocess scan 留 hook 层兜底（纵深防御） |
| Q4 | routing log 写 .audit/routing_log.jsonl 还是加 T4 adapter 接口 | **加 AuditAdapter 接口 + FileAuditAdapter v0.5 实装** · 类似 T2 KeyProvider 范式 · `ClickHouseAuditAdapter.skel` 留 T4 实施 · 防 T3→T4 集成时 server_v2 二次大改 |

### vendor_family 映射表（初版）

```yaml
openai: [gpt-5, o1, o1-mini, o1-codex, gpt-4o, ...]
anthropic: [claude-opus-4.7, claude-sonnet-4.6, claude-haiku-4.5, ...]
deepseek: [deepseek-v4-pro, deepseek-v3, ...]
alibaba: [qwen-32b, qwen-max, qwen-long, ...]
google: [gemini-2.5-pro, gemini-flash, ...]
xai: [grok-3, ...]
```

详 `mcp/model-router/vendor_families.yml` (T3 实现)。

---

## ADR-05 · 离线包结构：单 tarball + 子目录 docker images / wheels / models

### 决策
一个 `medharness-offline-v0.5.0-edge-linux-amd64.tar.gz`，内含：

```
medharness-offline-v0.5.0-edge/
├── VERSION
├── install.sh           # 入口
├── verify.sh            # 自动验证
├── teardown.sh          # 卸载
├── upgrade.sh           # 从老版本升
├── docker-compose.yml   # production 编排
├── images/              # docker load 用 · *.tar
│   ├── medharness-mcp-phi-detector.tar
│   ├── medharness-mcp-desensitize.tar
│   ├── ... (8 个 MCP)
│   ├── clickhouse-24.tar
│   ├── qdrant-1.x.tar
│   └── nginx.tar
├── wheels/              # offline pip · pip download --no-binary :none:
├── models/              # spaCy zh_core_web_sm + presidio default
├── configs/             # docker-compose env / .env.example / nginx.conf
├── data-seed/           # 合成示例 + 空 ClickHouse schema
├── docs-offline/        # mkdocs static build
├── runbooks/            # 10 个运维 runbook
├── checksum/
│   ├── SHA256SUMS
│   └── SHA256SUMS.asc   # GPG 签
└── LICENSE
```

### 替代
- A) 多个 tarball 分开下 → 客户串联难
- B) docker-compose pull from 内置 registry → 客户内网无 registry
- C) 用 OCI registry 内置（distribution:2） → 复杂、客户不熟

### 否决理由
A 客户体验差；B 大多内网无 registry；C 引入新依赖。
单 tarball + `docker load` 是医疗内网最稳的路径。

### 实施约束
- tarball < 6 GB（base layer 复用让 image 总和 < 5 GB）
- 支持 `docker load` 或 `push 到客户 harbor` 两路径（install.sh 提供 flag）
- buildx 同时产 linux/amd64 + linux/arm64（arm64 给开发机 demo）

---

## ADR-06 · TLS：self-signed + 客户自带 CA 双路径

### 决策
默认 install.sh 用 `gen-tls.sh` 生成 self-signed cert，nginx 反代。
客户可 `install.sh --cert /path/ca.crt --key /path/ca.key` 用自己 CA 签的证书。

### 替代
- A) 强制 Let's Encrypt → 客户内网无外网，ACME 走不通
- B) 强制客户 BYO cert → 演示门槛高
- C) HTTP 默认 → 监管会问

### 否决理由
A 不可行；B 演示门槛；C 监管。
双路径平衡：默认能用，正经客户必 BYO。

### 实施约束
- self-signed 默认 365 天，过期前 30 天 install.sh 检测告警
- 文档明示 self-signed 仅 demo，生产**必须** BYO
- mTLS（service-to-service）暂不强制，v1.0 加

### T11 codex Q&A 落档（2026-05-25）

| # | 问题 | 答 |
|---|---|---|
| Q1 | TLS 版本支持范围 | **TLS 1.2 + TLS 1.3 only** · TLS 1.0/1.1 deprecated by IETF RFC 8996 |
| Q2 | Cipher suite tier 选择 | **Mozilla SSL Config "intermediate"** · 兼容老 client (Android 5+ / iOS 9+ / IE 11) · 比 modern 宽 |
| Q3 | Cert subject CN 默认值 | **medharness.local** · 客户可通过 `MEDHARNESS_TLS_CN` 覆盖 |
| Q4 | Cert 输出路径 | **/etc/medharness/tls/{cert.pem,key.pem}** · host volume mount 跟 ADR-09 风格一致 · key chmod 600 |
| Q5 | check-cert-expiry exit code 分级 | **三档健康等级 + invalid**: 0=OK (>30d) · 1=warn (≤30d) · 2=critical (≤7d) · 3=missing/invalid · 跟 cron monitoring 兼容 |
| Q6 | HSTS 配置 | **max-age=31536000 (1 year) + includeSubDomains** · 跟 OWASP 推荐一致 · 不加 preload (`medharness.local` 不会进浏览器 preload list) |
| Q7 | install.sh --cert/--key BYO 接口 | **T11 不实施 install.sh** · 仅明示接口契约 · T13 offline build 集成时调 `gen-tls.sh` (默认 self-signed) 或 mount BYO cert path |

### T11 实施约束（codex Q&A 后补充）

- `gen-tls.sh` 用 `openssl req -x509 -newkey rsa:4096 -nodes -days 365` · SAN 含 `DNS:medharness.local` + `DNS:localhost` + `IP:127.0.0.1`
- `check-cert-expiry.sh` 用 `openssl x509 -noout -enddate` 解析 + BSD/GNU date 双兼容计算 `days_left`
- `nginx.conf`:
  - 80 server: `/health` endpoint 保留 HTTP · 其他 path 301 redirect HTTPS
  - 443 server: `ssl_protocols TLSv1.2 TLSv1.3` + Mozilla intermediate cipher suite
  - HSTS: `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`
  - Security headers: `X-Content-Type-Options nosniff` / `X-Frame-Options DENY` / `X-XSS-Protection`
  - OCSP stapling 关闭 (self-signed 没 OCSP responder · BYO CA-signed 时启用)
- compose mount: `${TLS_CERT_DIR:-/etc/medharness/tls}:/etc/medharness/tls:ro`
- T13 集成 `install.sh --cert/--key` 接口示例:

  ```bash
  # T13 install.sh 调用范式 (T11.1 仅明示接口 · T13 实施)
  install.sh --cert /path/to/ca.crt --key /path/to/ca.key
  # → 跳过 gen-tls.sh · 用 BYO cert 启动 compose
  ```

---

## ADR-07 · prompt-injection 防御：纯规则 detector + 5 类攻击家族 + 95% 阻断率

### 决策
v0.5.0 用**纯规则 + 关键字 + 上下文规则** detector 模块（`mcp/prompt-injection-scan/`）做 prompt-injection 防御：

1. **独立 MCP 模块**：跟 phi-detector 职责分离（PHI 是数据敏感，injection 是行为对抗）
2. **5 类攻击家族**：indirect injection / tool abuse / role escalation / jailbreak phrasing / encoding-obfuscation
3. **20+ 合成 corpus**：100% synthetic JSONL · 不抄真实越狱 prompt 库
4. **drill 4 gate**：阻断率 ≥ 95% · run_all.sh enforce

### 替代
- A) LLM-based 分类器（zero-shot prompt classifier） → 离线包不可，需要外部模型推理
- B) 集成进 mcp/phi-detector → 威胁模型混淆（PHI 检测 vs 行为对抗）
- C) 引入真实 jailbreak prompt library（如 jailbreakchat.com 数据） → R4 合规风险 + 攻击向量 PR 泄漏
- D) 阻断率阈值 80%（业界 baseline） → v0.5.0 corpus 100% synthetic，detector 见过同类模式，95% 可达且防 regression

### 否决理由
A 不离线；B 职责混淆；C 合规风险；D 太低不防 regression。
纯规则 + 5 类 + 95% 是 v0.5.0-edge 最匹配的组合。

### 实施约束
- detector 接口：`detect_injection(text: str, context: dict | None = None) → DetectionResult`
- DetectionResult schema：`{blocked, category, score, matched_rules, reason}`
- 8-12 条上下文规则（phi-detector 是 6 条 · injection 攻击模式更多样故略多）
- corpus 20+ cases · 5 类各 4+ cases · 含中英多语言 + obfuscation
- JSONL fixture 格式（跟 drill 3 一致：`tests/red-team-drills/fixtures/prompt_injection_corpus.jsonl`）
- drill 4 gate 在 `run_all.sh` enforce block_rate ≥ 0.95 · failed_case_ids 必须空
- 模块 stdlib-only · 不引入新 Python 依赖
- v0.6+ follow-up：引入真实 jailbreak corpus 时阈值降到 85% 并校准 ROC

### T7 codex Q&A 落档（2026-05-24）

| # | 问题 | 答 |
|---|---|---|
| Q1 | detector API 单一入口还是多 detector classes | **单一 `detect_injection(text, context=None)` → DetectionResult** · 内部 modular 多 detector category · 跟 phi-detector 单 detect() + 多 recognizer 范式一致 · DetectionResult 含 category 字段标明命中哪类 |
| Q2 | 3 baseline 之外还需哪些攻击家族 | **5 类**：indirect injection / tool abuse / role escalation + **jailbreak phrasing**（"DAN" / "ignore all previous" / "developer mode"）+ **encoding/obfuscation**（base64 / Unicode homoglyphs / ZWJ chars）· markdown/HTML/JSON-escape/multilingual 推迟 v0.6+（每类下加 1-2 中英混合 case 即可） |
| Q3 | 上下文规则数量 | **8-12 条** · 平衡 interpretability vs brittle · phi-detector 是 6 条 · injection 攻击模式更多样 · 太少漏报，太多维护难 |
| Q4 | 95% 阻断率阈值确认 | **95% 保持** · 20 cases × 95% = 最多漏 1 个 · v0.5.0 corpus 100% synthetic detector 可达 · 高门槛防 regression（每次改 detector 必须保持高准确）· v0.6+ 引入真实 jailbreak corpus 时阈值降到 85% 重新校准 ROC |
| Q5 | fixture 格式 JSONL vs YAML | **JSONL** · 跟 drill 3 (T4.9) 一致 · 复用 `_load_fixture` / `_write_jsonl` 模式 · 易 grep / wc -l / diff · attack case schema 简单（不需 YAML 表达力） |

### T7 实施约束（codex Q&A 后补充）
- corpus case schema：`{case_id, attack_family, text, expected_block, rationale}`
- 5 类 × 4+ cases = 20+ 起步（可按 RFC 加 expected-allow benign controls 测 FP，但 v0.5.0 优先级低）
- v0.5.0 只测 block rate；FP rate 留 T7 v0.6+ follow-up
- detector 内部规则按 attack_family 分组组织（防 7+ rule 互相干扰）
- LOGGER 不打印 detector 输入 text 内容（防 injection payload 泄漏到 audit）

---

## ADR-08 · 8 MCP Docker 镜像化：multi-stage + 非 root + per-MCP 依赖切片 + Trivy 扫

### 决策
v0.5.0 给 8 个 MCP server 各产一个 Dockerfile（**不含 prompt-injection-scan**，那是 detector library）：

1. **统一 base image**：`python:3.11-slim`（各 Dockerfile 各自 FROM，不抽 medharness-base · Docker engine base layer 自动复用）
2. **Multi-stage**：builder 装 build deps + pip wheel · runtime 复制必要 artifact + 非 root
3. **非 root user**：`medharness:medharness` UID/GID 9000 统一
4. **HEALTHCHECK 分级**：production MCP 优先调真 health endpoint · stub MCP 用 import smoke
5. **LABEL**：version (from 根 VERSION 文件) + SPDX (Apache-2.0) + maintainer
6. **依赖切片**：每个 MCP 自己 requirements.txt · 根 requirements.txt 保留为 union
7. **Vulnerability scan**：Trivy (`--severity HIGH,CRITICAL`) · 0 high vuln 为 gate

### 替代
- A) 共享 prebuilt medharness-base image → 引入 build 依赖顺序 + T13 offline 需额外 export base
- B) 全局 requirements.txt → image bloat（phi-detector 的 presidio 不该装到 model-router）
- C) Anchore / Snyk / Docker Scout → 需要 cloud account（医疗内网部署不友好）
- D) GitHub CodeQL → 是源码分析不是 image scan，不适用
- E) Build-time download spaCy zh model → 模型 85MB + 网络依赖 + image 超 500MB
- F) 全部用 import smoke 跳过真 endpoint health → production MCP blast radius 大

### 否决理由
A 复杂；B image 超限；C/D 离线不友好；E 模型超限 + 联网依赖；F production 不可接受。
multi-stage + 非 root + per-MCP slice + Trivy + 分级 HEALTHCHECK 是 v0.5.0-edge 最匹配的组合。

### 实施约束
- 8 MCP Dockerfile：phi-detector / desensitize / model-router / audit-log（4 生产）+ ci-trigger / internal-kb / pm-bridge / vector-db（4 stub）
- 根 VERSION 文件由 T9.1 创建（T13 tarball 也用同一份）
- Build/size 测试用 `scripts/docker-build.sh` + `scripts/docker-build-all.sh` shell 范式（跟 T4.6 setup-worm.sh / T4.7 verify-hashchain.sh 一致）
- CI 集成：`.github/workflows/docker-build.yml`（paths trigger + Trivy scan + image size assertion）
- 生产 MCP < 500MB · stub < 200MB
- spaCy zh model **不进 image**（T1 已用 RegexOnlyNlpEngine workaround）· T13 offline tarball 含 model 作为 optional bundle
- .dockerignore 必须排除 `.env` / `*.key` / `tests/red-team-drills/output/` / `AUDIT_BUNDLE_*.tar.gz` / `__pycache__/`

### T9 codex Q&A 落档（2026-05-24）

| # | 问题 | 答 |
|---|---|---|
| Q1 | 共享 prebuilt base vs 各自 FROM | **各自 `FROM python:3.11-slim`** · Docker engine base layer 自动复用 · 不引入"先 build base 再 build MCP"依赖顺序 · T13 offline 友好（不需 export 中间 base image） |
| Q2 | Version label 来源 | **根 VERSION 文件**（T9.1 创建）· Dockerfile `COPY VERSION /VERSION` + `LABEL version=$(cat /VERSION)` · 跟 T13 tarball VERSION 同一份 · 不依赖 CI build-arg · 本地/CI build 一致 |
| Q3 | requirements 全局 vs per-MCP | **per-MCP requirements.txt + 根全局 union** · phi-detector 装 presidio · model-router stdlib only（image 应 < 100MB）· desensitize 仅 cryptography · audit-log v0.5.0 mock-only（v0.6+ 加 clickhouse-connect）· stub 几乎无依赖 |
| Q4 | Stub HEALTHCHECK 设计 | **stub 用 import smoke** (`python -c "import server"`) · **production 优先真 health endpoint**（如 server_v2.py CLI `health` 子命令）· 不支持的 production fallback import smoke 并标 v0.6+ 升级到真 endpoint |
| Q5 | Vulnerability scanner 选 | **Trivy** (aquasec/trivy-action) · OSS · 离线友好（医疗内网部署可本地跑）· 覆盖 OS 包 + Python 依赖 + Dockerfile misconfig · 输出 SARIF + JSON · `--severity HIGH,CRITICAL` 当 "0 high vuln" gate |
| Q6 | Docker build tests 在哪跑 | **`scripts/docker-build.sh <mcp_name>` + `scripts/docker-build-all.sh` + `.github/workflows/docker-build.yml`** · 跟 setup-worm.sh / verify-hashchain.sh 范式一致 · 本地 dev + CI 共享同一 script · pytest subprocess docker build 太慢不适合 |
| Q7 | spaCy/Presidio 模型打包 | **build-time 装 presidio 包 + RegexOnlyNlpEngine workaround**（T1 commit 8753d41 已决策）· **spaCy zh_core_web_sm 不进 image** · T13 offline tarball 含 model 作为 optional bundle（客户内网部署时可选启用） |

### T9 实施约束（codex Q&A 后补充）
- 根 `VERSION` 文件格式：单行 semver（如 `0.5.0-edge`）· T9.1 创建
- `.dockerignore` 统一一份在根目录（被 8 Dockerfile 共享 build context）
- per-MCP requirements 命名：`mcp/<name>/requirements.txt`
- builder stage `pip install --no-cache-dir -r requirements.txt --target /wheels`
- runtime stage `COPY --from=builder /wheels /app/wheels` + `pip install --no-deps /app/wheels/*`
- runtime stage `USER medharness:medharness` 必须在 `WORKDIR /app` 之后
- HEALTHCHECK production 模式：`CMD python server_v2.py health || exit 1` · stub 模式：`CMD python -c "import server" || exit 1`
- LABEL 至少 3 字段：`org.opencontainers.image.version` / `org.opencontainers.image.licenses=Apache-2.0` / `org.opencontainers.image.source=https://github.com/charliehzm/medharness`
- T9.7 scripts/docker-build-all.sh 输出 JSON 报告含 image name / size / trivy summary

---

## ADR-09 · docker-compose.prod 编排：双网 + host volumes + nginx DMZ + per-service resource limits

### 决策
v0.5.0 用 `deploy/docker-compose.prod.yml` 编排 8 MCP + 1 nginx 反代：

1. **双网络拓扑**：`medharness_internal` (internal: true · 8 MCP 互通) + `medharness_dmz` (默认 · 仅 nginx)
2. **Host-mounted volumes**：`/data/medharness/audit/` + `/data/medharness/keystore/` 物理可控（医疗内网客户硬要求）
3. **Nginx DMZ entrypoint**：唯一 publish 端口的 service · upstream 走 internal DNS（service name）
4. **Per-service resource limits**：`deploy.resources.limits` (compose v3) · 生产 512MB-1GB / stub 256MB · 30 人公司单 host 部署
5. **Healthcheck 链**：`depends_on` + `condition: service_healthy` · model-router 依 phi-detector + desensitize
6. **环境变量**：`.env.production.example` commit · 真 `.env.production` gitignore + dockerignore

### 替代
- A) Kubernetes manifest → 客户内网无 k8s 集群 · 复杂度过高
- B) docker-compose v2 legacy `mem_limit` → 不推荐 · v3 spec 现代标准
- C) 单网络 + port publish 全 MCP → 攻击面大 · 不符合 medical compliance
- D) Named volume (Docker 管理) → 客户审计要求物理路径可见
- E) ClickHouse 容器现在启用 → 跟 ADR-08 Q3 "v0.5.0 mock-only" 冲突 · 推迟 v0.6+

### 否决理由
A 过度工程；B legacy；C 攻击面；D 不符合可审计要求；E 跟 audit-log 容器化决策冲突。
双网 + host volume + nginx DMZ + v3 resource limits 是 v0.5.0-edge 最匹配的组合。

### 实施约束
- `deploy/` 目录在 repo 根 · 含 docker-compose.prod.yml + nginx/medharness.conf + .env.production.example
- `medharness_internal` driver: bridge · `internal: true` · 8 MCP 仅在此网
- `medharness_dmz` driver: bridge · 默认（非 internal）· 仅 nginx 在此网 + internal 双 attach
- Host volumes: `/data/medharness/audit/` + `/data/medharness/keystore/` (跟 ADR-02 / ADR-03 / ADR-08 一致)
- 8 MCP 默认不 publish 端口 · 仅 nginx publish 80 (T10) + 443 占位 (T11 真启)
- Image tag 用 `${VERSION}` 从 .env.production.example 读 (跟 T9.7 build-arg VERSION 一致)
- HEALTHCHECK 链：model-router depends_on phi-detector + desensitize (condition: service_healthy)
- nginx depends_on model-router + audit-log + 4 stub (condition: service_healthy)
- audit-log 独立 (state machine 自管 · NORMAL/FALLBACK/BACKFILL)
- Resource limits per-service:
  - phi-detector: 1024MB mem / 1 cpu (presidio + spacy 最重)
  - desensitize / model-router / audit-log: 512MB mem / 0.5 cpu
  - 4 stub: 256MB mem / 0.25 cpu
  - nginx: 128MB mem / 0.25 cpu
  - 总占用：约 4-5 GB mem / 4 cpu · 单 host 30 人公司部署友好
- 验证级别：静态 yaml parse + 可选 `docker compose config` · 不跑 `up --wait`（CI 慢 + macOS dev 不一致 · 留 T13 offline install）

### T10 codex Q&A 落档（2026-05-25）

| # | 问题 | 答 |
|---|---|---|
| Q1 | Compose 文件格式 version | **不写 version** · Docker Engine 20.10+ Compose Spec 已不需要 · 写了反而被 warn |
| Q2 | T10 现在启用 ClickHouse 容器 vs mock-only | **暂不启用 · T10 mock-only** · 延续 ADR-08 Q3 audit-log v0.5.0 mock-only 决策 · v0.6+ 加 clickhouse service + audit-log requirements 改 |
| Q3 | nginx upstream 用 internal DNS vs 固定 IP | **internal DNS（service name）** · 跟 docker network 自带 DNS 集成 · 重启不需 reconfig · DNS lookup 走 docker embedded resolver |
| Q4 | image tag 用 `${VERSION}` / .env / 硬编码 | **`${VERSION}` 从 .env.production.example 读** · 跟 T9.7 build-arg VERSION 一致 · 部署时复制 .env.production.example → .env.production 改值 |
| Q5 | 最低验证级别 | **静态 yaml parse + 可选 `docker compose config`** · 不跑 `up --wait`（CI 慢 + macOS dev `docker compose` 行为不一致）· `up --wait` 真启动验证留 T13 offline install 测试 |
| Q6 | Resource limits 语法 | **`deploy.resources.limits` (compose v3 spec)** · 现代标准 · `mem_limit/cpus` 是 v2 legacy 不用 · 客户审计时 deploy.resources 字段一目了然 |
| Q7 | env / secrets 模板方式 | **`.env.production.example` commit · 真 `.env.production` 进 .dockerignore + .gitignore** · 客户部署时复制 .example 改值 · 不存 secret 到 git · 跟 12-factor app 一致 |
| Q8 | nginx 443 现在暴露 vs 等 T11 | **T10 暴露 80（HTTP 临时）+ 443 占位（comment-out）** · T11 TLS 完成后切真 443 + redirect 80→443 · T10 不 ship 真 cert (chicken-and-egg 问题) |

### T10 实施约束（codex Q&A 后补充）
- Compose 文件**无** `version:` 顶层字段（现代 spec 默认）
- nginx.conf upstream 写法：`upstream model_router { server model-router:8000; }` 用 service name
- nginx 端口映射：T10 `"80:80"` (HTTP only) + `# "443:443"` 注释占位 + T11 改 active
- .env.production.example 字段：`VERSION=0.5.0-edge` + 各 service 配置占位
- .env.production 必须加进 .dockerignore + .gitignore（防 commit）
- ClickHouse service 不在 T10 compose · 由 audit-log container 内 FileFallbackWriter 兜底
- 测试断言：
  - 8 MCP services + 1 nginx = 9 total services
  - 仅 nginx 有 `ports:` 字段
  - medharness_internal 含 `internal: true`
  - 每 service 有 `deploy.resources.limits.{memory,cpus}` + `restart_policy`
  - host volume paths 全在 `/data/medharness/*` 下

---

## 附录：决策映射到任务

| ADR | 影响任务 |
|---|---|
| ADR-01 | T1（phi-detector v3） |
| ADR-02 | T2（desensitize KMS） |
| ADR-03 | T4（audit-log WORM）+ T6（drill 3 audit replay · 部分 absorbed by T4.9） |
| ADR-04 | T3（model-router）+ T5（drill 2 · absorbed by T3.8） |
| ADR-05 | T13-T15（offline build） |
| ADR-06 | T11（TLS · 跟 ADR-09 nginx 443 占位接力） |
| ADR-07 | T7（prompt-injection drill 4） |
| ADR-08 | T9（8 MCP Dockerfile）+ T10（docker-compose）+ T13-T15（offline 含 image） |
| ADR-09 | T10（docker-compose.prod 编排）+ T11（TLS 接 nginx 443） |

详 [tasks.md](tasks.md)。
