# Spec · F1 · Console 基座 `web/`（React + TS + Vite）

> 前端 lane（Codex #2）· 实现前必读。**F1 必须先冻结接口，F2/F3 才能开工。**

---

## Purpose

把 `prototype/console-demo.html` 的设计落成真正的 React 应用骨架：脚手架 + 设计 tokens + 共享组件库 + 路由 + api-client（连 A0 契约 mock）。产出一个**样板视图**（合规·安全态势）作为 F2/F3 的结构范本。

## 技术栈（ADR-16 锁定）

- React 18 + TypeScript + Vite
- 路由：react-router
- 状态：Zustand 或 Context（**不引 Redux 全家桶**）
- 样式：CSS Modules / vanilla-extract + 设计 tokens（**不引 antd / MUI 等重型 UI 库**）
- app root：新建 `web/`；`prototype/console-demo.html` 保留作设计基准对照

## 目录约定

```
web/
  src/
    api/
      contract/   🔒 A0 契约 schema + 类型（单 owner 维护，FE 只 import）
      client.ts      照契约封装的 api-client（默认连 mock）
    design/       tokens（色板 navy/teal/violet · 间距 · 圆角 · 阴影）
    components/   Card Badge Tag Table Toast StatusDot RingScore ...
    views/        F2/F3 各视图（每视图独立目录）
    app/          shell + 路由 + 角色切换
```

## 设计 tokens（从原型抽）

- `--navy #0B1F3A` `--teal #0FB5A6`（合规青绿）`--violet #7C3AED`（安全紫罗兰）
- 状态：green/yellow/red；卡片圆角 14px、阴影、字体栈与原型一致
- 双色语义：**合规=teal、安全=violet** 贯穿全 Console

## 共享组件（对照原型）

Card / SectionTitle / Badge / Tag(L2/L3/L4) / CatChip(comp|sec) / StatusDot(g/y/r) / RingScore / Table / Toast / WipBadge(🚧 v0.6) / Sankey（可后置到 F2）

## Constraints（合规验收项 · ADR-17）

- C1 · DOM / React state / localStorage / sessionStorage **0 PHI**：只占位符 + 哈希 + 聚合
- C2 · api-client **禁止**把响应写入持久化存储（localStorage/sessionStorage）；含运行时守卫
- C3 · URL / query param **不带任何敏感数据**
- C4 · 安全事件组件**只渲染分类与处置**，绝不渲染 payload（契约里 payload 恒 null，前端也不得拼接）
- C5 · 错误边界 / 报错文案**不泄露系统版本 / 栈 / 内部路径**
- C6 · 顶栏「本页 0 PHI」徽标常驻；未建能力（出站/配额）渲染 🚧 v0.6
- C7 · 不引入第三方 cookie / 不弹条款（内网工具）

## 样板视图（F1.6）

把「合规·安全态势」迁成 React：综合分环 + 合规分/安全分下钻 + 闸门两组（合规已上线 / 安全防线含 🚧）+ 双类告警。数据走 api-client → A0 `/posture` mock。作为 F2/F3 抄的范本。

## DoD

- 基座目录 + 组件库 + 路由 + api-client 接口**冻结**（F2/F3 可依赖）
- 样板态势视图照 `/posture` mock 渲染正确
- `npm run build` 通过；ESLint/TS 无 error
- 合规自检通过：grep 全仓 `web/` 0 PHI；localStorage/URL 无敏感数据；安全事件无 payload 渲染
