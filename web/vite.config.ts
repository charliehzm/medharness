import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      // INT-5/6 dev 连调: in live mode the FE fetches relative /api/v1/* — forward
      // it to a locally-running A0 (scripts/int5_console_smoke.sh --keep exposes
      // it on :19000). Override target via VITE_A0_TARGET.
      "/api/v1": {
        target: process.env.VITE_A0_TARGET || "http://127.0.0.1:19000",
        changeOrigin: true,
      },
    },
  },
});
