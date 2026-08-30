import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.ANGMOO_UI_E_SETTINGS_PORT ?? "3104");
const baseURL = process.env.ANGMOO_UI_E_SETTINGS_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./ui-e-local-settings",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 45_000,
  workers: 1,
  expect: {
    timeout: 10_000,
  },
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    trace: "retain-on-failure",
    viewport: { width: 436, height: 880 },
  },
  webServer: process.env.ANGMOO_UI_E_SETTINGS_BASE_URL
    ? undefined
    : {
        command: `pnpm --dir ../frontend dev --hostname 127.0.0.1 --port ${port}`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        url: baseURL,
      },
});
