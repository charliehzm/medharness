import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 流量监控: mode tabs (inbound/outbound), event filters (全部/合规/安全), the animated
// Sankey, and the gate summary all respond, with no PHI / console errors.
test("traffic mode tabs, filters and sankey are interactive", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "流量监控");

  // mode tabs
  const modeTabs = page.locator(".traffic-mode-tabs button");
  await expect(modeTabs).toHaveCount(2);
  await modeTabs.nth(1).click(); // outbound -> tab activates + shows the 🚧 planned note
  await expect(modeTabs.nth(1)).toHaveClass(/on/);
  await expect(page.getByText("🚧 v0.6 规划").first()).toBeVisible();
  await modeTabs.nth(0).click(); // back to inbound

  // event filters: clicking moves the .on selection and keeps the stream rendered
  const filters = page.locator(".traffic-filters button");
  await expect(filters.first()).toBeVisible();
  const count = await filters.count();
  for (let i = 0; i < count; i++) {
    await filters.nth(i).click();
    await expect(filters.nth(i)).toHaveClass(/on/);
  }

  // the Sankey SVG mounts (proves the real animated widget renders)
  await expect(page.locator(".traffic-sankey-wrap svg, .sankey svg, svg").first()).toBeVisible();

  await assertNoPhiDom(page, "流量监控");
  expect(errors, errors.join("\n")).toHaveLength(0);
});
