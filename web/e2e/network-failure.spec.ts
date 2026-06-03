import { expect, test } from "@playwright/test";

import { gotoScreen, login, routeA0Down, switchRole } from "./fixtures";

// With the A0 data path intercepted (500), every screen must render its error state
// gracefully — never a blank crash, never a leak. Console errors from the failed
// fetch ARE expected here, so this spec asserts the error UI, not zero-errors.
const SCREEN_ERRORS: ReadonlyArray<readonly [string, string]> = [
  ["总览", ".overview-error"],
  ["流量监控", ".traffic-error"],
  ["审计与报表", ".audit-error"],
  ["用量与成本", ".cost-error"],
  ["接入", ".access-error"],
  ["系统", ".system-error"],
];

test("every screen renders its error state when A0 is down", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  await routeA0Down(page, "error"); // all /api/v1/* now 500

  for (const [label, errorSelector] of SCREEN_ERRORS) {
    await gotoScreen(page, label); // nav is client-side; the app shell still renders
    await expect(page.locator(errorSelector), `${label} error state`).toBeVisible({ timeout: 10000 });
  }
});
