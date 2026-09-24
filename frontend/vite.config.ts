/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 1500 },
  define: { global: "globalThis" },
  test: {
    environment: "jsdom",
    testTimeout: 30000,
    hookTimeout: 30000,
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["tests/integration/**"],
  },
});
