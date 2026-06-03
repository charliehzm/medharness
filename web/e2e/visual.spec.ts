import { expect, test } from "@playwright/test";

import { gotoScreen, login, switchRole } from "./fixtures";

// Visual regression — a full-page snapshot of every screen, per browser engine
// (chromium/firefox/webkit get their own baselines automatically). Animations are
// disabled (config). Per-run-dynamic regions — event timestamps, hashed admin ids,
// today's traffic — are MASKED so the diff tracks LAYOUT, charts, colours and chrome
// rather than data churn. Baselines are captured on the local render env; this suite
// is local-only (it drives the running stack), so cross-OS render drift is moot.
//
// Regenerate baselines after an intended UI change:
//   MEDHARNESS_LIVE_BASE=https://localhost:18443 bun run e2e -- visual.spec.ts --update-snapshots
const SCREENS: ReadonlyArray<readonly [string, readonly string[]]> = [
  ["总览", []], // posture scores are deterministic from the seed; gates are static
  ["流量监控", [".events"]], // event stream carries live timestamps
  ["审计与报表", [".dtable-scroll"]], // table rows carry timestamps
  ["用量与成本", []], // static cost payload
  ["接入", [".dtable-scroll"]], // admin id_hashes vary per run
  ["策略", []], // static config sections
  ["系统", [".system-list"]], // upstream "today" counters
];

test("every screen matches its visual baseline", async ({ page }) => {
  await login(page);
  await switchRole(page, "研发负责人");
  for (const [label, maskSelectors] of SCREENS) {
    await gotoScreen(page, label);
    await page.waitForTimeout(900); // let canvas/SVG widgets fully paint
    const mask = maskSelectors.map((s) => page.locator(s));
    // Viewport-only (not fullPage): a data-driven dashboard's total height drifts as
    // rows are added (e.g. the audit export appends a row earlier in the run), which
    // would shift a full-page capture. A fixed-height viewport snapshot + masked
    // dynamic regions tracks the above-the-fold layout/charts/chrome stably.
    await expect(page).toHaveScreenshot(`screen-${label}.png`, { mask });
  }
});
