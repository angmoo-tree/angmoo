import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.ANGMOO_CHARACTER_PREVIEW_URL ?? "http://127.0.0.1:3338";
const mode = process.env.ANGMOO_CHARACTER_STATIC === "1" ? "static-export" : "next-preview";
const suffix = process.env.ANGMOO_CHARACTER_EVIDENCE_SUFFIX;
if (suffix && !/^[a-z0-9-]{1,40}$/.test(suffix)) throw new Error("invalid_character_evidence_suffix");
const evidence = suffix ? `${mode}-${suffix}` : mode;
export default defineConfig({
  testDir: ".", testMatch: ["world-character-dashboard.spec.ts", "world-character-management.spec.ts", "profile-relationship-avatar.spec.ts", "world-character-lifetime.spec.ts"],
  workers: 1, fullyParallel: false, retries: 0, timeout: 60_000,
  outputDir: `../artifacts/world-character-management-20261005/${evidence}`,
  reporter: [["list"], ["json", { outputFile: `../artifacts/world-character-management-20261005/${evidence}-results.json` }],
    ["junit", { outputFile: `../artifacts/world-character-management-20261005/${evidence}-results.xml` }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: mode, use: { baseURL } }],
});
