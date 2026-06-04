import { expect, test } from "@playwright/test";

import { gotoScreen, login, switchRole } from "./fixtures";

// Responsive — the Console is a desktop/tablet B2B tool. Key screens must not break
// into a horizontal scroll at desktop or tablet widths; mobile (390px) is captured
// for review (a fixed-width console legitimately degrades there, so it is not a hard
// gate). Runs on chromium only — layout reflow is engine-independent here.
test.skip(({ browserName }) => browserName !== "chromium", "responsive layout check runs once on chromium");

const KEY_SCREENS = ["总览", "流量监控", "用量与成本", "接入"];

async function horizontalOverflow(page: import("@playwright/test").Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

for (const vp of [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 834, height: 1112 },
] as const) {
  test(`no horizontal overflow at ${vp.name} (${vp.width}px)`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await login(page);
    await switchRole(page, "研发负责人");
    for (const label of KEY_SCREENS) {
      await gotoScreen(page, label);
      await page.waitForTimeout(400);
      expect(await horizontalOverflow(page), `${label} @ ${vp.name} overflows`).toBeLessThanOrEqual(6);
    }
  });
}

test("mobile (390px) still renders each screen without crashing", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await switchRole(page, "研发负责人");
  for (const label of KEY_SCREENS) {
    await gotoScreen(page, label);
    await expect(page.locator(".topbar h1")).toBeVisible();
  }
});
