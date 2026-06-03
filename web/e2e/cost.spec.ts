import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 用量与成本: KPI cards, the by-lane/by-model bar charts, the cost-guard ring, the
// trend chart and the channel table all render (canvas widgets prove real render).
test("cost screen renders KPIs, charts, guard ring and channel table", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "用量与成本");

  await expect(page.locator(".cost-grid-kpi")).toBeVisible();
  await expect(page.locator(".cost-grid-guard")).toBeVisible();
  // VChart canvases mount for the bar + trend charts
  await page.waitForTimeout(700);
  await expect(page.locator(".cost-chart canvas").first()).toBeVisible();
  await expect(page.locator(".dtable tbody tr").first()).toBeVisible(); // channel table

  await assertNoPhiDom(page, "用量与成本");
  expect(errors, errors.join("\n")).toHaveLength(0);
});
