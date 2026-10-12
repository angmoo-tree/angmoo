import {defineConfig,devices} from "@playwright/test";
export default defineConfig({
  testDir:".",testMatch:"chat-world-real.spec.ts",workers:1,retries:0,timeout:90_000,expect:{timeout:30_000},
  reporter:[["list"],["json",{outputFile:"../artifacts/chat-world-lifecycle-20261012/real-browser-results.json"}]],
  outputDir:"../artifacts/chat-world-lifecycle-20261012/real-browser",
  use:{...devices["Desktop Chrome"],baseURL:"http://127.0.0.1:3419",serviceWorkers:"block",trace:"retain-on-failure",screenshot:"only-on-failure"},
  webServer:[
    {command:"pnpm --dir ../frontend start --hostname 127.0.0.1 --port 3415",env:{ANGMOO_NEXT_DIST_DIR:".next-chat-world-lifecycle"},url:"http://127.0.0.1:3415",reuseExistingServer:false,timeout:60_000},
    {command:"node fixtures/chat-world-real-proxy.mjs",url:"http://127.0.0.1:3419",reuseExistingServer:false,timeout:30_000},
  ],
});
