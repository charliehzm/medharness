import { expect, test } from "@playwright/test";

import { assertNoPatientPhiDom, gotoScreen, login, switchRole } from "./fixtures";

// The sysadmin user-management view legitimately shows STAFF identities — internal
// operators, NOT patients (usernames, and emails where present). This spec makes the
// 0-PHI carve-out explicit and BOUNDED: staff identity + the management affordances
// render, but NO patient identifier (cn-id / mobile) ever appears. The patient-0-PHI
// guarantee on every other screen is unchanged (those specs keep the email-inclusive
// scan). admin lands as 系统管理员 — do NOT switch to 研发负责人 here.
test("sysadmin user management shows staff identity but never patient PHI", async ({ page }) => {
  await login(page);
  await expect(page.locator(".role-select button.on")).toContainText("系统管理员");
  await gotoScreen(page, "接入");
  await page.locator('.access-tabs button:has-text("用户与分组")').click();

  // the management table renders real operator accounts (staff username is visible)
  await expect(page.locator(".dtable")).toContainText("admin");
  // the sysadmin-only create affordance opens its modal
  const createBtn = page.getByRole("button", { name: "新建用户" });
  await expect(createBtn).toBeVisible();
  await createBtn.click();
  await expect(page.locator(".access-modal")).toBeVisible();
  await page.locator(".policy-modal-close").click();
  await expect(page.locator(".access-modal")).toBeHidden();

  // patient identifiers must NEVER appear here, even though staff identity does
  await assertNoPatientPhiDom(page, "接入·用户管理");
});

test("research-lead gets the redacted view, not the user-management affordances", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  await gotoScreen(page, "接入");
  await page.locator('.access-tabs button:has-text("用户与分组")').click();
  // rdlead sees the redacted id_hash table — no create-user button
  await expect(page.getByRole("button", { name: "新建用户" })).toHaveCount(0);
});
