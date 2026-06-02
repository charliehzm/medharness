import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Reuse the app's "@" -> src alias; scope vitest to *.spec.ts so it never tries
// to run the node:test guards (*.test.ts, e.g. sanitize.test.ts).
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    include: ["src/**/*.spec.ts"],
    environment: "node",
  },
});
