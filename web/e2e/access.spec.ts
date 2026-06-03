import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 接入: the four tabs (应用/通道/令牌/用户) switch content; the admin tables show only
// hashed identifiers (no email / phone / display name) — the 0-PHI admin guarantee.
test("access tabs switch and admin tables stay 0-PHI", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "接入");

  const tabs = page.locator(".access-tabs button");
  await expect(tabs.first()).toBeVisible();
  const count = await tabs.count();
  expect(count).toBeGreaterThanOrEqual(3);
  for (let i = 0; i < count; i++) {
    await tabs.nth(i).click();
    await expect(tabs.nth(i)).toHaveClass(/on/);
    await assertNoPhiDom(page, `接入·tab${i}`); // every tab's data path stays 0-PHI
  }

  expect(errors, errors.join("\n")).toHaveLength(0);
});
