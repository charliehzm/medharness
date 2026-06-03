import { expect, test } from "@playwright/test";

import { CONSOLE_USER, login } from "./fixtures";

test("valid login lands in the console with the 0-PHI badge", async ({ page }) => {
  await login(page);
  await expect(page.locator(".phi-badge")).toContainText("全程 0 PHI");
});

test("wrong password shows a generic error and stays on /login", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input.login-input[type="text"]', CONSOLE_USER);
  await page.fill('input.login-input[type="password"]', "definitely-wrong-xyz");
  await page.click(".login-btn.primary");
  await expect(page.locator(".login-error")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("lock returns to the login screen", async ({ page }) => {
  await login(page);
  await page.click(".lock");
  await expect(page.locator(".login-input").first()).toBeVisible();
});
