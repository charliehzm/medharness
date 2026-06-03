import { expect, test } from "@playwright/test";

import { login, switchRole } from "./fixtures";

// admin -> sysadmin: sees 总览/用量与成本/接入/系统; 流量监控/审计与报表/策略 are locked.
test("admin lands as 系统管理员 with three locked screens", async ({ page }) => {
  await login(page);
  await expect(page.locator(".role-select button.on")).toContainText("系统管理员");
  await expect(page.locator(".nav-item")).toHaveCount(7);
  await expect(page.locator(".nav-item.disabled")).toHaveCount(3);
  await expect(page.locator(".nav-item:not(.disabled)")).toHaveCount(4);
});

test("研发负责人 unlocks all seven screens", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  await expect(page.locator(".nav-item.disabled")).toHaveCount(0);
  await expect(page.locator(".nav-item:not(.disabled)")).toHaveCount(7);
});
