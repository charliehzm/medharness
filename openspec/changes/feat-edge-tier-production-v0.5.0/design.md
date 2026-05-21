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
- 性能：< 5ms overhead per call
- 配置：`MODEL_ALLOWLIST.json` 热加载（不重启 router）

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

---

## 附录：决策映射到任务

| ADR | 影响任务 |
|---|---|
| ADR-01 | T1（phi-detector v3） |
| ADR-02 | T2（desensitize KMS） |
| ADR-03 | T4（audit-log WORM） |
| ADR-04 | T3（model-router）+ T5（drill 2） |
| ADR-05 | T13-T15（offline build） |
| ADR-06 | T11（TLS） |

详 [tasks.md](tasks.md)。
