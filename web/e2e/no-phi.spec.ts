import { test } from "@playwright/test";

import { SCREENS, assertNoPhiDom, gotoScreen, login, switchRole } from "./fixtures";

// DOM-level 0-PHI: the live data path (ClickHouse -> A0 BFF -> Console) must leak
// no PHI to the rendered page on any screen (complements the byte-level API scan).
test("no console screen leaks PHI in the rendered DOM", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  for (const label of SCREENS) {
    await gotoScreen(page, label);
    await page.waitForTimeout(400);
    await assertNoPhiDom(page, label);
  }
});
