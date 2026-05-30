# MedHarness 系统设计（System Design）

> **职责**：把产品设计（PRD / 产品形态 / UI / 高保真原型）落成**可实施的系统设计**——架构、后端、前端三份。
> **状态**：**定稿 v1（实现基线）** · 内容锁定，供 Step 2 任务拆解 + Codex 前/后端开发。
> **异构合规闸门 = WAIVED**（[r1](REVIEW-r1-codex.md) 设计级 + [r2](REVIEW-r2-codecheck.md) 代码级）：**B1/H2/M1/H3 已代码闭环 + 测试**（2026-05-31 · in-repo findings 全 CLOSED）；剩 B4(fork 延迟实测)/B5(new-api 字段 + A0 后端) 外部门禁（**B6 ✅ 已满足**：new-api 完全授权已获 2026-05-31）+ **r3 异构复审**确认运行态闭环，才可 WAIVED→签字。双委员会会签 pending。
> **维护**：技术委员会 + 合规委员会会签。

---

## 三份文档

| 文档 | 职责 | 读者 |
|---|---|---|
| [01-architecture.md](01-architecture.md) | 产品运行态系统架构：new-api fork 底座 + 合规控制面 + 数据存储 + Console；请求路径脊柱（Hook 强制顺序）、分级路由、审计链、部署拓扑、建/缺口 | 架构师 / 技委 / 合规委 |
| [02-backend-design.md](02-backend-design.md) | 后端设计：网关焊接（pre/post 闸门）、6 控制面服务、A0 聚合 API 实现、数据模型、PolicyCore、KMS、fail-closed | 后端 Coder-Agent / 后端工程师 |
| [03-frontend-design.md](03-frontend-design.md) | 前端设计：Console（web/）技术栈、IA/路由、A0 契约层 + `Sanitized<T>` 0-PHI 守卫、逐屏组件↔API 映射、RBAC、登录 | 前端 Coder-Agent / 前端工程师 |

## 上游锚点（产品 / 决策）

- 产品定位 + 四目标（**安全 · 划算 · 审计 · 稳定**）：[../productization/console-product-design.md](../productization/console-product-design.md)
- 统一需求源（PRD）：[../productization/product-requirements.md](../productization/product-requirements.md)
- UI 视觉/交互规范：[../productization/ui-design.md](../productization/ui-design.md)
- 高保真原型（设计基准）：[../../prototype/console-demo.html](../../prototype/console-demo.html)
- 底座选型 RFC（**r4 锁 new-api · r5 单 SKU**）：[../architecture/gateway-substrate-selection.md](../architecture/gateway-substrate-selection.md)
- 统一网关 + ADR-11（egress 唯一强制点）：[../architecture/unified-gateway.md](../architecture/unified-gateway.md)

## 一句话边界

> 本系统 = **new-api 深度 fork（网关底座，Go）** + **合规控制面（6 个 Python 服务：检测/脱敏/路由/审计/注入/出站）** + **ClickHouse/Redis/KMS** + **MedHarness Console（自建 React 应用，经 A0 只读聚合 API 读数，全程 0 PHI）**。底座负责"接得广、跑得稳、算得清"；我们死磕"分级路由 + 脱敏 + 出入站安全 + 防篡改审计 + 异构治理"。
