# feat-edge-tier-production-v0.5.0 · change 入口

> **接手者必读**：从这里开始 5 分钟搞清楚。

---

## 一句话

把 v0.1.0-alpha 推到 **v0.5.0-edge**——单实例 + 真合规 + 离线部署包，给中小医疗 SaaS / 互联网医院做 PoC。
不是 v1.0（M6 才上 HA + WORM Object Lock + SBOM + SLA）。

---

## 读这 5 份文件，按顺序

1. [proposal.md](proposal.md) · 为什么做、做什么、不做什么、验收
2. [COMPLIANCE_TAG.md](COMPLIANCE_TAG.md) · Step 0 三方签字（必先签）
3. [design.md](design.md) · 6 条关键架构决策（ADR）
4. [tasks.md](tasks.md) · 20 任务 · 4 phase · 3-5 周
5. [specs/](specs/) · 3 个核心 spec（phi-detector / audit-log-worm / offline-build）

---

## 4 phase 节奏

```
Phase 1 · 合规底层（week 1-2）        T1-T4
Phase 2 · 红队 + 评估（week 2-3）      T5-T8
Phase 3 · 部署编排（week 3-4）         T9-T12
Phase 4 · 离线打包 + 文档（week 4-5）  T13-T20
```

详 [tasks.md](tasks.md)。

---

## SOP 路径

每个任务**单独走 12 步主通道**，不是 5 步 micro（触及 PHI / 模型 / 审计的代码均跨多文件）。

每个 task 一个 OpenSpec sub-change：`openspec/changes/feat-edge-tier-production-v0.5.0/T<N>-<short>/`

---

## 出口（验收）

- [ ] 真实部署在干净 Ubuntu 22.04 / CentOS Stream 9 上跑通 install.sh
- [ ] verify.sh 跑通：dryrun e2e + 红队 4/4 drill + recall ≥ 92%
- [ ] AUDIT_BUNDLE 6 个月内可重放（手动触发一次）
- [ ] tarball 体积 < 6GB
- [ ] 卸载 teardown.sh 后 0 残留（docker volume / image / network 全清）
- [ ] 运维 runbook 10 个常见操作可被新人按步骤完成
- [ ] 监管审计应对 4h 内交付 demo

---

## 当前状态

- 起点：main = 47f74ca（v0.1.0-alpha · CI 全绿）
- 目标：分支 `feat/edge-tier-production-v0.5.0` → 20 个 PR 渐进合入
- 责任：codex 实现 / charliehzm review + Compliance 签字 / Claude Code 偶尔兜底

---

## 不能做的事（不可让步）

- ❌ 改 LICENSE / 改 5 红线
- ❌ 跳过 12 步 SOP
- ❌ 任何 PR 让 PHI 真实数据进 fixtures
- ❌ Compliance-Agent 用 Coder 同模型家族
- ❌ 直接 push main（强 BP · 1 review）
- ❌ self-merge PR（即使 CI 全绿）
- ❌ 用云 LLM 直连（必经 mcp-model-router）
- ❌ 在公共仓库引入任何真实客户配置
