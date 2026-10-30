import {defineConfig, devices} from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: "maintenance-recovery.spec.ts", workers:1, retries:0, timeout:60000,
  expect:{timeout:15000}, outputDir:"../artifacts/maintenance-recovery/browser",
  reporter:[["list"],["json",{outputFile:"../artifacts/maintenance-recovery/browser-results.json"}]],
  use:{...devices["Desktop Chrome"],baseURL:"http://127.0.0.1:3382",timezoneId:"Asia/Seoul",serviceWorkers:"block",trace:"retain-on-failure",screenshot:"only-on-failure"},
  webServer:{command:"pnpm --dir ../frontend dev --port 3382 --hostname 127.0.0.1",url:"http://127.0.0.1:3382",reuseExistingServer:false,timeout:120000},
});
