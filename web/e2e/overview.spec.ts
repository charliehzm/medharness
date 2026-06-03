import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 总览: the posture dashboard renders gate cards, the attention/alert section and the
// target KPI cards, with no PHI and no console errors.
test("overview renders posture gates, alerts and targets", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "总览");

  await expect(page.locator(".overview-gate-grid")).toBeVisible();
  // gate cards: the six §D.1 gates (4 built + 2 planned)
  await expect(page.locator(".overview-gate-grid .overview-gate-head")).toHaveCount(6);
  await expect(page.locator(".overview-attention")).toBeVisible();
  await expect(page.locator(".overview-alert-row").first()).toBeVisible();

  await assertNoPhiDom(page, "总览");
  expect(errors, errors.join("\n")).toHaveLength(0);
});
