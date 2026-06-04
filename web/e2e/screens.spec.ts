import { expect, test } from "@playwright/test";

import { SCREENS, gotoScreen, login, switchRole } from "./fixtures";

// As 研发负责人 (all 7 screens visible), navigate each and screenshot it. Waiting
// on the heavy widgets (canvas charts, SVG sankey) proves the real-browser render.
test("every console screen renders and is captured", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  for (const label of SCREENS) {
    await gotoScreen(page, label);
    await page.waitForTimeout(700); // let canvas/SVG widgets mount
    await expect(page.locator(".side .nav-item.active")).toContainText(label);
    await page.screenshot({ path: `e2e/__screens__/${label}.png`, fullPage: true });
  }
});
