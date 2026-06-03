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

export type A0DownMode = "abort" | "error";

// Drive the Console's A0 data path "down" by intercepting its /api/v1/* reads, so a
// screen renders its error state WITHOUT touching the shared container (reversible,
// per-test, no cross-test bleed). Apply AFTER login (login itself hits /api/v1/auth).
export async function routeA0Down(page: Page, mode: A0DownMode = "abort"): Promise<void> {
  await page.route("**/api/v1/**", (route) => {
    if (mode === "error") {
      void route.fulfill({
        status: 500,
        contentType: "application/json",
        body: '{"error":{"code":"data_source_unavailable","msg":"data source unavailable"}}',
      });
    } else {
      void route.abort();
    }
  });
}

// Collect pageerror + console.error so a spec can assert a screen renders with zero
// uncaught errors. Returns a live array (read it at teardown).
export function captureConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console.error: ${m.text()}`);
  });
  return errors;
}
