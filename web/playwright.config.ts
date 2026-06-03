import { defineConfig, devices } from "@playwright/test";

// Layer 1 — UI E2E against the DEPLOYED Console behind the nginx DMZ. The
// chart/canvas/SVG/particle views can't render in jsdom, so this drives a real
// Chromium against the running stack. Not wired into `bun test` (vitest stays
// offline); run explicitly: MEDHARNESS_LIVE_BASE=https://localhost:18443 bun run e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.MEDHARNESS_LIVE_BASE || "https://localhost:18443",
    ignoreHTTPSErrors: true, // self-signed DMZ cert
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
