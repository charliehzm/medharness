import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 系统: the upstream-health list renders one row per upstream and the maintenance
// action buttons (备份/升级/审批) are present.
test("system screen renders upstream health and action buttons", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "系统");

  await expect(page.locator(".system-list")).toBeVisible();
  await expect(page.locator(".system-row").first()).toBeVisible();
  await expect(page.locator(".system-actions button").first()).toBeVisible();

  await assertNoPhiDom(page, "系统");
  expect(errors, errors.join("\n")).toHaveLength(0);
});
