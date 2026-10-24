import { defineConfig, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
const output = process.env.ANGMOO_PHOTO_TEST_OUTPUT ?? "../artifacts/photo-input";
mkdirSync(output, { recursive: true });
export default defineConfig({
  testDir: ".", testMatch: ["photo-input.spec.ts", "photo-input-paths.spec.ts", "memory-subject-policy.spec.ts", "no-role-language.spec.ts", "creator-copy-media.spec.ts", "creator-copy-ui.spec.ts"],
  grepInvert: /home font|single column preview|package export|studio draft metadata|creation completion actions/,
  workers: 1, retries: 0, timeout: 90_000, expect: { timeout: 15_000 },
  outputDir: `${output}/browser`, reporter: [["list"], ["json", {outputFile: `${output}/browser-results.json`}]],
  use: { ...devices["Desktop Chrome"], actionTimeout: 15_000, serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next", use: { baseURL: "http://127.0.0.1:3404" } }, { name: "static-export", use: { baseURL: "http://127.0.0.1:3405" } }],
});
