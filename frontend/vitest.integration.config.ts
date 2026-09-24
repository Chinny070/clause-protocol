import { defineConfig } from "vitest/config";

// Real-runtime contract integration (local GenLayer simulator). Not part of `npm test`.
export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: ["tests/integration/**/*.test.ts"],
    testTimeout: 240000,
    hookTimeout: 240000,
  },
});
