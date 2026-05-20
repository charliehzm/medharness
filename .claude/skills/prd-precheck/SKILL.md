---
name: prd-precheck
description: >
  ALIAS · 别名 Skill。本 Skill 在 v2.1 起被合并到 `prd-implementation-precheck`。
  保留本文件仅用于兼容老 SOP 引用；新代码应改用主 Skill。
deprecated: true
canonical: prd-implementation-precheck
metadata:
  version: "1.0-alias"
  owner: "product-line"
  category: "spec-alias"
  maturity: "deprecated"
  alias_of: "prd-implementation-precheck"
---

# prd-precheck（别名 → prd-implementation-precheck）

> v2.1 合并决议：v2.0 审计发现本 Skill 与 `prd-implementation-precheck` 触发场景 90% 重叠，开发者选错率 70%（M1 沙盘 W1 D3）。

## 立即跳转
请调用 [`prd-implementation-precheck`](../prd-implementation-precheck/SKILL.md)。

## 为什么留这个文件
- 兼容研发交付SOP v1（v1 第 1 步 Skill 名是 `prd-implementation-precheck`，本 Skill 是 v2.0 误命名的"短名"）
- M5 全员推广后删除，回收命名空间
