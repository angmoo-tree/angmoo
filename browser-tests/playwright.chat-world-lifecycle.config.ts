import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: ["chat-world-lifecycle.spec.ts", "image-integration.spec.ts", "world-chat-dialog-delete.spec.ts", "creator-copy-ui.spec.ts"],
  grep: /Chat typing|World lifecycle|accepted analysis failure offers explicit text recovery|T38-T39\/T46 room|T47 old deletion cannot redirect|T47 late 401|T47 pending delete cannot survive navigation|T47 a successful old deletion|world crop cancel, dimensions|World image transport failure and removal/,
  workers: 1, fullyParallel: false, retries: 0, timeout: 60_000, expect: { timeout: 15_000 },
  reporter: [["list"], ["json", { outputFile: "../artifacts/chat-world-lifecycle-20261012/browser-results.json" }]],
  outputDir: "../artifacts/chat-world-lifecycle-20261012/browser",
  use: { ...devices["Desktop Chrome"], serviceWorkers: "block", screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [{name:"next",use:{baseURL:"http://127.0.0.1:3417"}}, {name:"static",use:{baseURL:"http://127.0.0.1:3418"}}],
  webServer: [
    {command:"pnpm --dir ../frontend start --hostname 127.0.0.1 --port 3415",env:{ANGMOO_NEXT_DIST_DIR:".next-chat-world-lifecycle"},url:"http://127.0.0.1:3415",reuseExistingServer:false,timeout:60_000},
    {command:"node ../frontend/scripts/serve-static.mjs --port 3416",url:"http://127.0.0.1:3416",reuseExistingServer:false,timeout:30_000},
    {command:"node fixtures/chat-world-lifecycle-server.mjs",url:"http://127.0.0.1:3417/__phase/audit",reuseExistingServer:false,timeout:30_000},
  ],
});
