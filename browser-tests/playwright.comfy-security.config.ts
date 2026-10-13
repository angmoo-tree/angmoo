import {defineConfig,devices} from "@playwright/test";
export default defineConfig({
  testDir:".",testMatch:["comfy-security-flow.spec.ts","comfy-editor-regression.spec.ts"],workers:1,fullyParallel:false,retries:0,
  timeout:90_000,expect:{timeout:20_000},reporter:[["list"],["json",{outputFile:process.env.ANGMOO_COMFY_REPORT??"../artifacts/comfy-security-20261012/browser-results.json"}]],
  outputDir:"../artifacts/comfy-security-20261012/browser",
  use:{...devices["Desktop Chrome"],trace:"retain-on-failure",screenshot:"only-on-failure"},
  projects:[{name:"next",use:{baseURL:"http://127.0.0.1:3440"}},{name:"static",use:{baseURL:"http://127.0.0.1:3441"}}],
});
