import { defineConfig, devices } from "@playwright/test";

// This suite starts its own Next and contributor backend on ephemeral ports.
export default defineConfig({
  testDir: ".",
  testMatch: "character-card-upload.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  use: { ...devices["Desktop Chrome"], trace: "retain-on-failure" },
});
