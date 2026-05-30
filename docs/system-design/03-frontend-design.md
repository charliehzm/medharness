# MedHarness Console 前端设计

> **状态**：DRAFT · 与代码现状对齐。**已建** = web/ React18 脚手架 + A0 契约层（v0.7.0）+ `Sanitized<T>` 0-PHI 守卫；**待建** = 设计 token/组件/壳/各屏（F1.2–F3）。
> **设计基准**：高保真原型 [../../prototype/console-demo.html](../../prototype/console-demo.html) + UI 规范 [../productization/ui-design.md](../productization/ui-design.md)。
> **数据契约**：A0 只读聚合 API [../../web/src/api/contract/](../../web/src/api/contract/)（前后端唯一耦合点）。

---

## 1. 前端策略决策（重要 · 需会签确认）

**现状**：`web/` 是**自建 React 18 应用**（Vite + react-router + 自建 A0 契约层 + `Sanitized<T>` 守卫），**不是** new-api 前端的 fork。但 ui-design §8 曾写"复用 new-api React19 + Semi Design，不重写组件层"。二者有张力，需明确。

**裁定（已确认）**：**Console 自建**，理由：
1. **0-PHI 守卫必须在我们代码里**——`Sanitized<T>` + `assertNoPhi` 是合规红线，不能依赖 new-api 前端。
2. 合规/观测屏（总览/流量/审计/策略）是护城河，原型即自建设计，无 new-api 对应页可复用。
3. **管理面**（接入：渠道/令牌/用户）走 **new-api 原生管理 API**（复用其后端能力），UI 在我们壳内重画——而非 fork 其前端。

> 即：**复用 new-api 的后端（网关/渠道/用户/计费 API），前端自建**。ui-design §8（及 §3 / 头注）已同步改为「复用 new-api 后端、前端自建」。React 版本以代码实际 **18** 为准（非 19）。

---

## 2. 技术栈

| 关注点 | 选型 | 现状 |
|---|---|---|
| 框架/语言 | React 18.3 + TypeScript 5.9 | ✅ [web/](../../web/) |
| 构建 | Vite 6 | ✅ |
| 路由 | react-router-dom 6 | ✅（未接屏） |
| 数据契约 | 自建 A0 contract 层（types/endpoints/mock/sanitize） | ✅ v0.7.0 |
| 图表 | **VChart**（双向桑基/成本图） | 🔴 待引（原型用纯 SVG，生产用 VChart） |
| 组件库 | 轻量自建（映射原型组件）或 Semi Design 选用 | 🔴 待定（F1.3） |
| 设计 token | ui-design §2 配色/字号/间距 → CSS vars | 🔴 待提（F1.2） |
| i18n | 暂硬编码中文，i18next 后置 | 后置 |

---

## 3. 缝：A0 契约层 + 0-PHI 守卫（已建·勿动）

`web/src/api/contract/`（🔒 单 owner，冻结）：

```
types.ts      8 响应类型 + 2 写口类型（PostureResponse/TrafficResponse/EventsResponse/
              AuditLineageResponse/UpstreamsResponse/ConfigSnapshot/AuditExport/ConfigPropose）
endpoints.ts  ENDPOINTS(GET×6+POST×2) + CONFIG_SECTIONS(10) + buildPath()
version.ts    CONTRACT_VERSION "0.7.0" · API_BASE "/api/v1"
mock.ts       resolveMock() 离线 mock（fixtures/ 全 0 PHI）
sanitize.ts   Sanitized<T> 品牌 + assertNoPhi(data,endpoint) + PhiLeakError
index.ts      barrel
```

**`Sanitized<T>` 守卫机制**：
- **类型层**：品牌类型（unique symbol `PHI_CHECKED`）——未过守卫的响应**无法**进 React state（编译期拦）。
- **运行层**：`assertNoPhi` 深遍历，扫 cn_id/cn_phone/email/bank_card/passport 模式 + 校验**安全事件 payload===null**；命中抛 `PhiLeakError`，只报 `{path,kind}`，**不含原文**。
- 与红队 drill [tests/red-team-drills/drill_api_phi_exfil.py](../../tests/red-team-drills/) 同模式，前后端双跑。

**数据获取约定**：所有响应（mock 或真实）**必须**先过 `assertNoPhi` 再进 state；api-client（F1.5）统一封装 `fetch → assertNoPhi → Sanitized<T>`。当前默认 mock，A0 后端就绪后切真。

---

## 4. ✅ 已解：用量与成本端点（A0 v0.7.0）

A0 契约 v0.6.1 原冻结于 **v0.6 双向 Console**（聚焦安全+审计），早于四目标重设计（把「划算」提为一等屏，新增 **💰 用量与成本**），缺成本端点。**本轮已决加性 bump 至 v0.7.0**，新增两只只读端点（**不破坏**现有 8 端点）：

| 新屏需要 | v0.7.0 端点 |
|---|---|
| 成本 KPI（本月成本/省比/缓存/日上限余量）+ 构成（通道/模型）+ 趋势 + 省钱建议 | `GET /cost?window=` → `CostResponse` |
| 渠道比价择优（价/延迟/区域/权重/健康） | `GET /channels` → `ChannelsResponse` |

成本全为聚合数，**天然 0 PHI**，照样过 `assertNoPhi`。类型见 [types.ts](../../web/src/api/contract/types.ts)，后端聚合见 [02 §6](02-backend-design.md)。已落契约代码（version 0.7.0 + types + endpoints + fixtures）。

---

## 5. 信息架构 / 路由 / 壳

**路由**（与原型 NAV 一致，按四目标分组）：
```
/login                         登录（OIDC/passkey · 科技感入口）
/  (= /overview)               🏠 总览          → /posture (+ /cost 摘要)
  【安全】 /traffic            📊 流量监控      → /traffic + /events
          /audit              🔍 审计与报表    → /events + /audit/{ref} + POST /audit/export
  【划算】 /cost              💰 用量与成本    → /cost + /channels（⚠️待契约）
          /access             🔌 接入          → /upstreams + new-api 管理 API
  【治理/运维】/policy         ⚙️ 策略          → /config/{section} + POST /config/{section}/propose
          /system             🛠 系统          → 健康/备份/升级（new-api + 控制面健康）
```
**壳**：`AppShell` = `SideNav`（品牌 + 四目标分组 + 角色门控）+ `TopBar`（环境 pill + 0 PHI 绿标 + 角色切换 + 🔒锁定）+ `<Outlet/>`。登录页独立全屏，登录后渲染壳。

---

## 6. RBAC（2 角色 · 导航即权限）

| 角色 | 落点 | 可见 | 越权项 |
|---|---|---|---|
| **研发负责人** | /overview | 全部 7 屏 + 审批 + 导出 | — |
| **系统管理员** | /access | 总览/用量成本/接入/系统 | 流量/审计/策略 **灰显🔒**（非隐藏）+ tooltip「需研发负责人」 |

实现：`ROLE[role].nav` 白名单 → `SideNav` 对不可见项加 `disabled` + 🔒（呼应原型 `renderNav`）；路由守卫 `go(v)` 越权重定向到 `land`。高危写口（如改 PHI 字段）即便可点也走审批（按钮文案随风险切「提交审批」）。

---

## 7. 逐屏 · 组件 ↔ A0 端点映射

| 屏 | 关键组件（原型出处） | A0 端点 | 0-PHI 要点 |
|---|---|---|---|
| **总览** | 四目标卡（环形分/KPI）· 6 闸门卡 · 需要注意（runbook 链）· 本月小结 | `GET /posture`（+ `/cost` 摘要） | `alerts[].payload` null；`gates[].built==false`→🚧 |
| **流量监控** | 双向桑基（VChart·入站/出站）· 双色事件流 · 三态过滤 | `GET /traffic` · `GET /events?cat=` | `outbound.built==false`→🚧；安全事件无 payload |
| **审计与报表** | 双色事件流 · 检索表 · 详情抽屉（血缘图+哈希链+脱敏请求/响应）· 导出监管包 | `GET /events` · `GET /audit/{ref}` · `POST /audit/export` | details.v 仅占位符/哈希/聚合 |
| **用量与成本** | 成本 KPI · 按通道/模型构成 · 渠道比价 · 护栏 · 省钱建议 | `GET /cost?window=` · `GET /channels`（v0.7.0） | 全聚合数，天然 0 PHI |
| **接入** | 接入应用 · 模型与渠道 · 令牌与配额 · **用户与分组（复用 new-api）** · 零改造 base_url | 读：`GET /upstreams`；CRUD：**new-api 管理 API** | 无转售入口；用户表区分 Console 2 角色 vs 仅令牌工程师 |
| **策略** | 合规/安全/成本护栏/治理审批 tab · DIFF 预览 · 审批弹窗（2 角色矩阵） | `GET /config/{section}`（10 section）· `POST /config/{section}/propose` | 写口只产 `approval_id`，**不直接改配置** |
| **系统** | 部署健康（ClickHouse/Redis/KMS/控制面）· 备份/升级 | new-api + 控制面健康（拟 `/system/health`） | — |
| **登录** | 科技感 hero（品牌+四目标+合规徽章）+ 玻璃拟态卡（OIDC/passkey） | new-api OIDC/passkey 认证 | 无自助注册/社交登录 |

> 配置 section ↔ 策略 tab：scene/models/fields/thresholds/retention→合规；injection/output→安全；quota→成本护栏；approval/upstream→治理/接入。

---

## 8. 设计 token（ui-design §2 → CSS vars · F1.2）

```css
--primary:#0B1F3A; --compliance:#0FB5A6; --security:#7C3AED;
--ok:#22C55E; --warn:#F59E0B; --bad:#EF4444; --cost:#A16207;
--lane-normal:#0FB5A6;   /* 常规通道 */  --lane-sensitive:#7C3AED; /* 敏感通道 */
```
- 健康分/四目标卡数字 = 唯一超大字号（40–96px 环形）。占位符/哈希/编号用等宽。
- **合规=青绿 / 安全=紫罗兰** 分色贯穿（铁律 7），事件流/桑基/闸门据此着色。
- 登录页例外：可比 in-app 更有张力（深色科技感），进入后回到「临床信任」克制基调。

---

## 9. 状态与数据流

- **请求层**：api-client（F1.5）`fetch(API_BASE+path) → assertNoPhi → Sanitized<T>`；失败渲染结构化错误（不显栈/版本）。
- **缓存/轮询**：观测屏（总览/流量）按 window 轮询（如 30s）；审计/配置按需拉。建议 React Query 或轻量 SWR（待定）。
- **mock↔真实**：env 开关 `resolveMock()`（离线开发/演示，全 0 PHI）↔ 真实 A0。Demo 默认 mock。
- **🚧 渲染**：凡 `built==false` 的 gate/能力，统一渲 `🚧 规划` 标 + 占位 mock，绝不冒充已建（诚实护栏）。

---

## 10. 管理面集成（接入屏 · new-api 后端）

接入屏的 CRUD（渠道/令牌/用户）**不经 A0**（A0 只读聚合），直接调 **new-api 原生管理 API**（fork 后继承）：
- 渠道：new-api channels（+ 我们加 `data_level`/`lane`/`region` 字段）。
- 令牌：new-api tokens（+ `allowed_data_levels`）。
- 用户/分组：new-api users/groups（仅 OIDC+passkey；映射 Console 2 角色；关自助注册/社交登录）。
- **移除转售 UI**：注册/支付/订阅/兑换/充值/钱包/社交登录页全不可达。

> 写操作仍受后端 Hook/审批约束；高危项经策略屏审批流。

---

## 11. 落地分期（F1–F3）与原型→生产映射

| 阶段 | 内容 | 状态 |
|---|---|---|
| **F1 Console 基座** | F1.1 脚手架✅ → F1.2 设计 token → F1.3 组件库 → F1.4 壳+路由 → F1.5 api-client → F1.6 样板屏(总览跑 mock) | 🟡 F1.1 done |
| **F2 观测屏** | 流量桑基(VChart) + 双色事件流 + 审计抽屉 + 导出 | 🔴 |
| **F3 配置/审计/接入** | 策略 DIFF+审批 + 接入(new-api) + 用户管理 + 系统 | 🔴 |
| **F4** | 用量与成本屏 + 登录页 + 对接 A0 `/cost`·`/channels`（v0.7.0 已加） | 🔴 |

**原型→生产**：原型（单文件 HTML，14KB CSS，纯 SVG）是**设计 + 交互基准**；生产按 token/组件/VChart 重画，IA/RBAC/文案/0-PHI 规则**逐条对齐原型**。差距约 85%（壳/组件/屏全待建，契约层已就绪）。

---

## 12. 开放项

1. ✅ **A0 cost 端点**——已 bump v0.7.0 加 `/cost`·`/channels`（§4，契约代码已落）。
2. ✅ **前端自建**确认；ui-design §8/§3/头注已同步。
3. 组件库：轻量自建 vs Semi Design——F1.3 定（开放）。
4. 系统屏健康端点契约（`/system/health`）——并入 A0 或独立（开放）。
5. 轮询/实时：观测屏是否上 SSE（依赖后端流式，Phase B）（开放）。
