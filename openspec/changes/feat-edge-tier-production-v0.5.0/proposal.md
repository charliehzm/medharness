# Proposal · feat-edge-tier-production-v0.5.0

> Step 1-3 产物。
> 提案日期：2026-05-21
> 提案人：charliehzm
> 状态：待 Compliance Officer + 技术 Lead 签字

---

## 1. 业务诉求

中小医疗 SaaS / 互联网医院 PoC 客户**等不到 M6 v1.0**。
他们要：
- 内网空气墙 → 离线部署包
- HIPAA / PIPL 合规底层真实工作（不能是 stub）
- 单个 PoC 公司、≤ 30 人团队规模
- 4 小时审计应对能力
- 不需要 HA / 复杂监控 / SLA 合同

v0.1.0-alpha 当前是"骨架 + stub"，距离上面诉求差 3-5 周工作量。
跳过等于让 anchor customer 流失。

## 2. 我们建议做

把项目推到 **v0.5.0-edge tier**：
- 介于 alpha（骨架）和 v1.0（企业级）之间
- 单实例 + 真合规底层 + 离线部署包
- 明确告知客户："不是 SLA-grade，是 PoC-grade"

20 个独立任务，4 phase，3-5 周。

## 3. 范围内（必做）

### Phase 1 · 合规底层真实现
1. **phi-detector v3 → Presidio backend**：真集成 + 31 fields.yml + Luhn + 6 上下文规则
2. **desensitize → cryptography.fernet + KMS 抽象**：先支持文件 keystore；BYO KMS 接口预留
3. **model-router → 真校验 allowlist + 异构性 runtime check + 熔断 + 限流**
4. **audit-log → ClickHouse 真写 + 哈希链 + chattr +a WORM 模拟**

### Phase 2 · 红队 + 评估
5. drill 2 router bypass 实现
6. drill 3 audit replay 实现
7. drill 4 prompt injection 实现
8. CI gate recall ≥ 92% · 月度 cron

### Phase 3 · 部署编排
9. 8 MCP server + 2 storage Dockerfile + 非 root 镜像
10. docker-compose.prod.yml + healthcheck + 网络隔离
11. TLS self-signed 生成工具 + nginx 反代
12. 备份 / 恢复 / 升级 / 卸载脚本

### Phase 4 · 离线打包 + 文档
13. `build-offline.sh`（macOS + Linux 双平台 buildx）
14. `install.sh`（无外网目标机 5 分钟起服务）
15. `verify.sh`（dryrun + 红队 + e2e 自动跑）
16. 镜像 cosign 签名 + tarball SHA256 + GPG 签名
17. 运维 runbook（10 个常见操作）
18. 监管审计应对包（4h 交付演练）
19. 离线包 e2e 验证（Lima / qemu 模拟空气墙）
20. v0.5.0-edge release + 配套博客 / 公告

## 4. 范围外（明确告知客户，避免误期望）

- ❌ HA 高可用 / 多副本 / 故障自动转移
- ❌ k8s helm chart（docker compose 够撑 30 人公司）
- ❌ Prometheus / Grafana 全栈监控（出结构化日志，客户自接 ELK / Loki）
- ❌ 完整 SBOM 流程（提供 syft 脚本，客户自跑）
- ❌ 多租户隔离（一家公司一个部署）
- ❌ 训练好的中文医疗 phi-detector（用 Presidio default + 31 规则，召回 92-96%）
- ❌ M6 商业版功能（托管 SaaS / 24x7 SLA / 1-on-1 督导）

## 5. 不可让步的边界

- 5 红线（R1-R5，见 CLAUDE.md）任一不让
- PHI 真实数据零进入仓库
- Compliance-Agent 与 Coder 异构性强制
- License 永久 Apache 2.0 / CC BY-SA 4.0
- 部署包**不内置任何真实客户配置**（customize.py 才生成 .local）

## 6. 衡量成功

| 指标 | 目标 |
|---|---|
| 离线部署成功率 | ≥ 95%（在 3 个目标 OS 上） |
| install.sh 总耗时 | ≤ 5 min（不含 docker load） |
| docker load 耗时 | ≤ 5 min |
| verify.sh 总耗时 | ≤ 8 min |
| PHI 检测 recall（合成 corpus） | ≥ 92% |
| Hook 误判率（合成 corpus） | ≤ 15% |
| AUDIT_BUNDLE 6 个月可重放 | 100% |
| tarball 体积 | < 6 GB |
| 4h 审计应对演练 | 通过 |
| 卸载残留 | 0 |

## 7. 风险与对冲

| 风险 | 概率 | 对冲 |
|---|---|---|
| Presidio 中文 recall 达不到 92% | 中 | M2 内提交上游 PR + 我们规则层弥补 |
| ClickHouse WORM 模拟被绕过 | 中 | chattr +a + 哈希链 + 第三方验签 ≥ 3 层 |
| 离线包体积超 6GB | 中 | 分层 image · base layer 单独打 · 增量更新 |
| KMS 抽象接口设计错 | 低 | 文件 keystore 先实现，云 KMS adapter v1.0 再补 |
| 客户期望 HA 但只给单实例 | 高 | 文档 + 销售话术明确"edge tier" |
| 部署到信创 OS 跑不起来 | 中 | 测试矩阵包含 UOS / 麒麟 |

## 8. 不在范围（避免 scope creep）

| 想做但本 change 不做 | 理由 | 留待 |
|---|---|---|
| Web UI / Dashboard | v0.6.0 起 | v0.6.0 |
| 训练好的 PHI 模型权重 | 训练数据 + 算力成本 | 商业版 |
| 自助 portal / 注册流程 | 商业版功能 | M10+ |
| 多集群联邦 | 不在 edge tier 定位 | v2.0+ |
| Mobile SDK | 不属医疗 AI Coding 体系 | 永不 |

## 9. 决策权 / 签字

| 角色 | 责任 | 签字 |
|---|---|---|
| 提案人 | charliehzm | ✅ 2026-05-21 |
| Compliance Officer | charliehzm（兼任） | ☐ |
| 技术 Lead | charliehzm | ☐ |
| Reviewer-Agent（异构） | Compliance-Agent（独立模型） | ☐ |

未三方签字 → 不进入 Phase 1。

## 10. 时间表

```
Week 1   T1-T2  phi-detector v3 + desensitize KMS
Week 2   T3-T4  model-router + audit-log WORM
Week 3   T5-T8  红队 drill 2-4 + CI gate
Week 4   T9-T12 Dockerfile + compose + TLS + 备份
Week 5   T13-T16 离线打包 + 签名
Week 5+  T17-T20 文档 + e2e 验证 + release
```

3 周快路径 / 5 周稳路径。

## 11. 关联

- 路线图：[docs/roadmap.md](../../../docs/roadmap.md)
- 架构图：[docs/architecture/dependency-graph.md](../../../docs/architecture/dependency-graph.md)
- 商业边界：[docs/community-vs-commercial.md](../../../docs/community-vs-commercial.md)

## 12. 后续

签字后 → codex 接手按 tasks.md 走 12 步 SOP 推进。
