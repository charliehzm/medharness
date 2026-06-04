import { expect, test, type Page } from "@playwright/test";

import { assertNoPatientPhiDom, gotoScreen, login } from "./fixtures";

async function assertNoSecretsOrPatientPhi(page: Page, where: string): Promise<void> {
  const html = await page.content();
  expect(html, `plaintext key marker on ${where}`).not.toContain("sk-");
  await assertNoPatientPhiDom(page, where);
}

test("sysadmin manages access apps and model channels without exposing secrets", async ({ page }) => {
  await login(page);
  await expect(page.locator(".role-select button.on")).toContainText("系统管理员");
  await gotoScreen(page, "接入");

  const suffix = Math.random().toString(36).slice(2, 7);
  const appName = `自动化接入应用${suffix}`;
  const channelName = `自动化模型渠道${suffix}`;

  await page.getByRole("button", { name: "新建接入应用" }).click();
  await page.getByLabel("应用名").fill(appName);
  await page.getByLabel("剩余配额").fill("180000");
  // Data levels are read-only (derived from the group), so there is nothing to tick here.
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.locator(".dtable")).toContainText(appName);
  await assertNoSecretsOrPatientPhi(page, "接入应用·新建");

  // The token row shows its derived data levels read-only (no 数据等级 edit action).
  const appRow = page.locator("tr", { hasText: appName });
  await expect(appRow).toContainText("L2");
  await expect(appRow.getByRole("button", { name: "数据等级" })).toHaveCount(0);

  await appRow.getByRole("button", { name: "改配额" }).click();
  await page.getByLabel("剩余配额").fill("220000");
  await page.getByRole("button", { name: "确认" }).click();
  await expect(appRow).toContainText("220000");
  await assertNoSecretsOrPatientPhi(page, "接入应用·改配额");

  await appRow.getByRole("button", { name: "停用" }).click();
  await page.getByRole("button", { name: "确认" }).click();
  await expect(appRow).toContainText("停用");

  await appRow.getByRole("button", { name: "删除" }).click();
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.locator(".dtable")).not.toContainText(appName);
  await assertNoSecretsOrPatientPhi(page, "接入应用·删除");

  await page.locator('.access-tabs button:has-text("模型与渠道")').click();
  await page.getByRole("button", { name: "新建渠道" }).click();
  // 从医疗模型目录预填: picking a template fills name/type/models for the operator.
  await page.getByLabel("从医疗模型目录预填").selectOption({ label: "DeepSeek 境内·常规便宜池 (L2)" });
  await expect(page.getByLabel("渠道名称")).toHaveValue("DeepSeek 境内·常规便宜池");
  await expect(page.getByLabel("模型", { exact: true })).toHaveValue("deepseek-v3");
  // then override with the synthetic test channel for the rest of the CRUD flow.
  await page.getByLabel("渠道名称").fill(channelName);
  await page.getByLabel("类型").fill("openai");
  await page.getByLabel("权重").fill("60");
  await page.getByLabel("模型", { exact: true }).fill(`model-${suffix}`);
  await page.getByLabel("服务地址").fill("https://gateway.example.test/v1");
  await page.getByLabel("密钥").fill(`sk-test-${suffix}`);
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.locator(".dtable")).toContainText(channelName);
  await assertNoSecretsOrPatientPhi(page, "模型与渠道·新建");

  const channelRow = page.locator("tr", { hasText: channelName });
  await channelRow.getByRole("button", { name: "编辑" }).click();
  await page.getByLabel("权重").fill("55");
  await page.getByRole("button", { name: "确认" }).click();
  await expect(channelRow).toContainText("55%");
  await assertNoSecretsOrPatientPhi(page, "模型与渠道·编辑");

  await channelRow.getByRole("button", { name: "测试渠道" }).click();
  await page.getByRole("button", { name: "确认" }).click();
  // The probe runs against an unreachable placeholder upstream → honest "不可达" verdict
  // (the operation succeeds; the modal stays open showing the result, then closes on 关闭).
  await expect(page.locator(".access-test-result")).toContainText("不可达");
  await assertNoSecretsOrPatientPhi(page, "模型与渠道·测试");
  await page.getByRole("button", { name: "关闭" }).click();
  await expect(page.locator(".access-modal")).toHaveCount(0);

  await channelRow.getByRole("button", { name: "删除" }).click();
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.locator(".dtable")).not.toContainText(channelName);
  await assertNoSecretsOrPatientPhi(page, "模型与渠道·删除");
});
