import { expect, test } from "@playwright/test";

import { captureConsole, gotoScreen, login, switchRole } from "./fixtures";

// 策略: tabs switch sections; editing a field surfaces a live DIFF; the propose flow
// opens the approval modal and submits (or cancels) — config writes go through
// approval, never a silent edit.
test("policy tabs, field-edit DIFF and the approval modal work", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "策略");

  // tabs switch
  const tabs = page.locator(".policy-tabs button");
  await expect(tabs.first()).toBeVisible();
  await tabs.nth(1).click();
  await expect(tabs.nth(1)).toHaveClass(/on/);
  await tabs.nth(0).click();

  // edit a field -> a DIFF line appears
  const field = page.locator(".policy-input").first();
  await expect(field).toBeVisible();
  await field.fill("9999");
  await expect(page.locator(".policy-diff-line").first()).toBeVisible();

  // open the approval modal, fill a reason, submit
  await page.locator(".policy-submit").first().click();
  await expect(page.locator(".policy-modal")).toBeVisible();
  await page.fill("#policy-reason", "e2e synthetic policy proposal");
  await page.click(".policy-modal-submit");
  // submission result shows an approval id (or the modal closes cleanly)
  await expect(page.locator(".policy-modal")).toBeHidden({ timeout: 10000 });

  expect(errors, errors.join("\n")).toHaveLength(0);
});

test("policy approval modal can be cancelled", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "策略");
  await page.locator(".policy-input").first().fill("1234");
  await page.locator(".policy-submit").first().click();
  await expect(page.locator(".policy-modal")).toBeVisible();
  await page.click(".policy-modal-cancel");
  await expect(page.locator(".policy-modal")).toBeHidden();
});
