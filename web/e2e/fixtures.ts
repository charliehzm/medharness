import { expect, type Page } from "@playwright/test";

export const CONSOLE_USER = process.env.MEDHARNESS_LIVE_USER || "admin";
export const CONSOLE_PASS = process.env.MEDHARNESS_LIVE_PASS || "medharness123";

// All seven Console screens (rdlead sees all; sysadmin only the first set).
export const SCREENS = ["总览", "流量监控", "审计与报表", "用量与成本", "接入", "策略", "系统"];

// Unambiguous PHI markers — the DOM must never contain these (mirrors the Python
// conftest 0-PHI patterns).
export const PHI_PATTERNS = [
  /[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]/, // cn id-18
  /(?<!\d)1[3-9]\d{9}(?!\d)/, // cn mobile
  /[\w.+-]+@[\w-]+\.[\w.-]+/, // email
];

export async function login(page: Page, user = CONSOLE_USER, pass = CONSOLE_PASS): Promise<void> {
  await page.goto("/login");
  await page.fill('input.login-input[type="text"]', user);
  await page.fill('input.login-input[type="password"]', pass);
  await page.click(".login-btn.primary");
  await expect(page.locator(".topbar h1")).toBeVisible();
}

export async function switchRole(page: Page, label: "研发负责人" | "系统管理员"): Promise<void> {
  await page.click(`.role-select button:has-text("${label}")`);
  await expect(page.locator(".role-select button.on")).toContainText(label);
}

export async function gotoScreen(page: Page, label: string): Promise<void> {
  const item = page.locator(`.nav-item:not(.disabled):has-text("${label}")`);
  await item.click();
  await expect(item).toHaveClass(/active/); // navigation landed on this screen
  await expect(page.locator(".topbar h1")).toBeVisible();
}

export async function assertNoPhiDom(page: Page, where: string): Promise<void> {
  const html = await page.content();
  for (const pattern of PHI_PATTERNS) {
    const match = html.match(pattern);
    expect(match, `PHI-like marker on ${where}: ${match?.[0]?.slice(0, 8)}`).toBeNull();
  }
}
