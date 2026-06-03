import { expect, test } from "@playwright/test";

import { assertNoPhiDom, captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 审计与报表: the table + search filter, a row-click that opens the lineage drawer
// (血缘 + 哈希链), and the regulator-bundle export — the full audit drill-down.
test("audit table filters, drills lineage and exports a bundle", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "审计与报表");

  const rows = page.locator(".dtable tbody tr");
  await expect(rows.first()).toBeVisible();
  const total = await rows.count();
  expect(total).toBeGreaterThan(0);

  // drill: click the first row -> lineage drawer with the hash-chain block
  await rows.first().click();
  await expect(page.locator(".audit-drawer")).toBeVisible();
  await expect(page.locator(".audit-detail-list")).toBeVisible();

  // search narrows the table: a non-matching token shows the empty state
  await page.fill(".audit-search input", "zzz-no-such-event-zzz");
  await expect(page.getByText("暂无匹配事件")).toBeVisible();
  await page.fill(".audit-search input", "");
  await expect(page.locator(".dtable tbody tr").first()).toBeVisible();

  // export the regulator bundle -> a result with a bundle id + sha256
  await page.click(".audit-export-button");
  await expect(page.locator(".audit-export-result")).toBeVisible({ timeout: 10000 });

  await assertNoPhiDom(page, "审计与报表");
  expect(errors, errors.join("\n")).toHaveLength(0);
});
