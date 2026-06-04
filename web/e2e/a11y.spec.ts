import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { gotoScreen, login, SCREENS, switchRole } from "./fixtures";

// Accessibility — axe-core scans every screen for WCAG violations. The gate is ZERO
// `critical`-impact violations (the bar a shipped console must clear); serious /
// moderate / minor findings are collected and printed for triage, not hard-failed.
// DOM-based, so it runs once on chromium.
test.skip(({ browserName }) => browserName !== "chromium", "a11y is DOM-based; run once on chromium");

test("no critical accessibility violations on any screen", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");

  const summary: Record<string, string[]> = {};
  const criticalsAll: string[] = [];

  for (const label of SCREENS) {
    await gotoScreen(page, label);
    await page.waitForTimeout(400);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    summary[label] = results.violations.map((v) => `${v.impact ?? "?"}:${v.id}(${v.nodes.length})`);
    for (const v of results.violations) {
      if (v.impact === "critical") criticalsAll.push(`${label} → ${v.id}: ${v.help}`);
    }
  }

  // Printed for triage regardless of pass/fail.
  console.log("a11y violations by screen:\n" + JSON.stringify(summary, null, 2));
  expect(criticalsAll, `critical a11y violations:\n${criticalsAll.join("\n")}`).toHaveLength(0);
});
