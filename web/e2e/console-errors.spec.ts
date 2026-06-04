import { expect, test } from "@playwright/test";

import { captureConsole, gotoScreen, login, SCREENS, switchRole } from "./fixtures";

// Navigating every screen on the happy path must produce ZERO uncaught page errors
// and ZERO console.error — a regression guard that the live data path renders each
// screen cleanly (the shallow smoke suite never instrumented this).
test("no screen logs a console error on the happy path", async ({ page }) => {
  const errors = captureConsole(page);
  await login(page);
  await switchRole(page, "研发负责人");

  for (const label of SCREENS) {
    await gotoScreen(page, label);
    await page.waitForTimeout(500); // let async widgets settle
  }

  expect(errors, `console errors:\n${errors.join("\n")}`).toHaveLength(0);
});
