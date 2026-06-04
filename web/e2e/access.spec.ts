import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 接入: the three tabs (应用/通道/用户) switch content; the admin tables stay 0-PHI.
test("access tabs switch and admin tables stay 0-PHI", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "接入");

  const tabs = page.locator(".access-tabs button");
  await expect(tabs.first()).toBeVisible();
  const count = await tabs.count();
  expect(count).toBe(3);
  await expect(tabs).toHaveText(["接入应用", "模型与渠道", "用户与分组"]);
  for (let i = 0; i < count; i++) {
    await tabs.nth(i).click();
    await expect(tabs.nth(i)).toHaveClass(/on/);
    await assertNoPhiDom(page, `接入·tab${i}`); // every tab's data path stays 0-PHI
  }

  expect(errors, errors.join("\n")).toHaveLength(0);
});
