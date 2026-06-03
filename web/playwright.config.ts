import { defineConfig, devices } from "@playwright/test";

// Layer 1 — UI E2E against the DEPLOYED Console behind the nginx DMZ. The
// chart/canvas/SVG/particle views can't render in jsdom, so this drives a real
// Chromium against the running stack. Not wired into `bun test` (vitest stays
// offline); run explicitly: MEDHARNESS_LIVE_BASE=https://localhost:18443 bun run e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: {
    timeout: 12_000,
    // Visual regression tolerance: kill animations (the Sankey/particle/orb views
    // never settle) and allow a small ratio for cross-render antialiasing. Baselines
    // are captured per-browser on the LOCAL render env (this suite is local-only).
    toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: "disabled", caret: "hide" },
  },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.MEDHARNESS_LIVE_BASE || "https://localhost:18443",
    ignoreHTTPSErrors: true, // self-signed DMZ cert
    screenshot: "only-on-failure",
  },
  // Cross-browser: the functional + visual specs run on all three engines. The
  // a11y + responsive specs self-restrict to chromium (DOM-/viewport-level checks
  // are engine-independent) via a guard on testInfo.project.name.
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
