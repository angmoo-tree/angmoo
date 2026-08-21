import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.ANGMOO_STATIC_E2E_PORT ?? "3200");

export default defineConfig({
  testDir: ".",
  testMatch: "static-product-shell.spec.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 45_000,
  workers: 1,
  expect: { timeout: 10_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://127.0.0.1:${port}`,
  },
  webServer: {
    command: `node ../frontend/scripts/serve-static.mjs --port ${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    url: `http://127.0.0.1:${port}`,
  },
});
