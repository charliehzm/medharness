# Spec · T4 · audit-log WORM 3 层防篡改

> 任务 T4 完整规格。codex 实现前**必读**。

---

## Purpose

把 `mcp/audit-log/server.py` 从 stub 改为真用 ClickHouse 写入 + 哈希链 + filesystem chattr +a 三层防篡改。
满足 HIPAA 6 年审计可重放要求。

---

## Inputs

```python
audit_event = {
    "event_id": str,                # uuid v4
    "timestamp": str,               # iso8601
    "actor": {
        "agent_role": str,          # coder / reviewer / compliance / pm / data-steward / memory-curator
        "model_id": str,            # 完整 model_id
        "vendor_family": str,       # openai / anthropic / deepseek / alibaba / google
        "session_id": str,
    },
    "action": {
        "tool": str,                # tool name
        "skill": str | None,        # SKILL.md name if applicable
        "operation": str,           # read / write / route / desensitize / detect
    },
    "context": {
        "change_id": str | None,    # openspec change id
        "step": int | None,         # 0-12 SOP step
        "data_levels": list[str],   # [L1, L2, L3, L4]
    },
    "result": {
        "status": str,              # success / blocked / error
        "reason": str | None,
        "duration_ms": float,
    },
    "input_hash": str,              # sha256 of input
    "output_hash": str,             # sha256 of output（不存原文）
}
```

## Outputs

成功写入：
```python
{
    "event_id": str,
    "row_id": int,                  # ClickHouse 内 ID
    "prev_hash": str,               # sha256 of (previous row)
    "current_hash": str,            # sha256 of (this row + prev_hash)
}
```

---

## Constraints

- C1 · 一次写入延迟 < 50ms（p99）
- C2 · 高并发 ≥ 1000 events/sec（单 ClickHouse 实例）
- C3 · 哈希链不可断（任一行改 → 后续全部失效）
- C4 · 文件层 append-only（chattr +a）
- C5 · 表层 append-only（DDL 禁 ALTER UPDATE / DELETE）
- C6 · 6 年保留（TTL > 6y）

---

## 3 层架构

### Layer 1 · ClickHouse 表层（强约束）

```sql
CREATE TABLE _audit_log (
    event_id UUID,
    timestamp DateTime64(3, 'UTC'),
    actor_agent_role LowCardinality(String),
    actor_model_id String,
    actor_vendor_family LowCardinality(String),
    actor_session_id String,
    action_tool String,
    action_skill Nullable(String),
    action_operation LowCardinality(String),
    context_change_id Nullable(String),
    context_step Nullable(UInt8),
    context_data_levels Array(LowCardinality(String)),
    result_status LowCardinality(String),
    result_reason Nullable(String),
    result_duration_ms Float32,
    input_hash FixedString(64),
    output_hash FixedString(64),
    prev_hash FixedString(64),
    current_hash FixedString(64),
    row_id UInt64,                  -- monotonic
    inserted_at DateTime64(3) DEFAULT now64()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, row_id)
TTL timestamp + INTERVAL 7 YEAR;    -- 6 年 + 1 年 buffer

-- 用户权限：仅 INSERT + SELECT
-- 永不授予 ALTER UPDATE / DELETE
GRANT INSERT, SELECT ON _audit_log TO medharness_audit_writer;
REVOKE ALTER UPDATE, ALTER DELETE FROM medharness_audit_writer;
```

### Layer 2 · 哈希链

- 每行 `current_hash = sha256(event_json || prev_hash)`
- `prev_hash` 取自上一行的 `current_hash`
- 链头：第 0 行 `prev_hash = "GENESIS"`（all zeros）
- 验链脚本：`scripts/verify-hashchain.sh`（每日凌晨 cron）

```python
def compute_hash(event: dict, prev_hash: str) -> str:
    canonical = json.dumps(event, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{canonical}|{prev_hash}".encode()).hexdigest()
```

### Layer 3 · Filesystem chattr +a

- ClickHouse 数据文件（`.parquet` parts）所在目录 chattr +a
- `chattr +a /data/medharness/clickhouse/_audit_log/`
- → 文件可创建 + 追加，**不可删除 / 修改**
- 即使 root 也 unsetable without `chattr -a`（root 操作必落 audit）

```bash
# scripts/setup-worm.sh
sudo chattr +a /data/medharness/clickhouse/_audit_log/
sudo chattr +a /data/medharness/audit-export/

# 验证
lsattr /data/medharness/clickhouse/_audit_log/
# 期望：-----a-------- ...
```

---

## 链完整性 verify（daily cron）

```bash
# scripts/verify-hashchain.sh
#!/usr/bin/env bash
set -e

clickhouse-client --query="
SELECT 
    row_id,
    prev_hash,
    current_hash,
    -- 重算 hash
    cityHash64(toString(event_id), toString(timestamp), ..., prev_hash) AS recomputed
FROM _audit_log
ORDER BY row_id
INTO OUTFILE '/tmp/verify-$(date +%Y%m%d).tsv' FORMAT TSV
"

python3 scripts/verify_hashchain_logic.py /tmp/verify-$(date +%Y%m%d).tsv \
    || { echo "🚨 HASH CHAIN BROKEN"; send_sev1_alert; exit 1; }
```

---

## Acceptance criteria

- AC1 · INSERT 性能 ≥ 1000 rows/sec（benchmark · single ClickHouse node）
- AC2 · 哈希链：插 10000 行 → verify 链通过
- AC3 · 故意篡改 1 行 → daily verify 检测出
- AC4 · DELETE / UPDATE 操作：权限拒绝（错误码 516 / 不可写）
- AC5 · chattr +a 后 `rm` parquet 文件失败
- AC6 · 6 个月历史数据可被 drill 3 audit replay 重放成功

---

## Failure modes

| 故障 | 行为 |
|---|---|
| ClickHouse 连接失败 | 重试 3 次 + 写本地 fallback 文件 `audit-fallback-<ts>.jsonl` |
| 哈希链断 | daily verify 报 SEV-1 + 阻断所有新写入（防扩散） |
| 磁盘满 | 写失败 → 调用方阻塞 + Compliance Officer 告警 |
| chattr 失败 | install.sh 启动时 fail-fast |

---

## ClickHouse 部署约束

- 版本：≥ 24.x（社区版 OSS）
- 持久化卷：`/data/medharness/clickhouse/` host 挂载
- 备份：daily 增量 + weekly 全量（T12 实现）
- 权限：医保 / 客户 audit 通常要求 audit DBA 独立于 app DBA → docker compose 提供 2 user 配置

---

## Non-goals

- 不上链到区块链 / 公证（v1.0 + 选项）
- 不实时同步到对象存储（v1.0 + 加 OSS Object Lock）
- 不做实时告警 / Splunk 集成（结构化日志够）
- 不加密 audit 内容（input_hash / output_hash 已脱敏；明文事件 metadata OK）

---

## Test plan

1. **Unit · hash chain logic**：`test_hashchain.py`
   - 生成 100 行 mock event → 链 verify pass
   - 篡改第 50 行 → 第 51+ verify fail
2. **Integration · ClickHouse**：`test_audit_log_integration.py`
   - 起 ClickHouse container → 插 10000 行 → 查询 → verify
   - DELETE 测试：期望失败
3. **Performance · benchmark**：
   - 1000 / 5000 / 10000 rows/sec
4. **Drill 3（T6 复用）**：6 个月模拟数据可重放

---

## Implementation hints

```python
# mcp/audit-log/server.py · 雏形
import clickhouse_driver
from hashlib import sha256

class AuditLogServerV2:
    def __init__(self, ch_host, ch_port, ch_user, ch_pass):
        self.client = clickhouse_driver.Client(
            host=ch_host, port=ch_port,
            user=ch_user, password=ch_pass,
            settings={"async_insert": 1}  # 高并发优化
        )
        self._last_hash = self._fetch_last_hash()
    
    def _fetch_last_hash(self) -> str:
        rows = self.client.execute(
            "SELECT current_hash FROM _audit_log ORDER BY row_id DESC LIMIT 1"
        )
        return rows[0][0] if rows else "0" * 64  # GENESIS
    
    def append(self, event: dict) -> dict:
        prev = self._last_hash
        canonical = json.dumps(event, sort_keys=True, ensure_ascii=False)
        current = sha256(f"{canonical}|{prev}".encode()).hexdigest()
        event["prev_hash"] = prev
        event["current_hash"] = current
        self.client.execute("INSERT INTO _audit_log VALUES", [event])
        self._last_hash = current
        return {"event_id": event["event_id"], "current_hash": current, "prev_hash": prev}
```

完整实现 codex 接手产出。
