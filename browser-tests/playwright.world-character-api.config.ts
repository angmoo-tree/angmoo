import { defineConfig, devices } from "@playwright/test";

const mode = process.env.ANGMOO_CHARACTER_STATIC === "1" ? "static-export" : "next-preview";
const basis = process.env.ANGMOO_CHARACTER_BASIS_KIND ?? "legacy_transition";
if (!["creation", "legacy_transition"].includes(basis)) throw new Error("unsupported_character_fixture_basis");
const evidence = basis === "creation" ? `${mode}-creation` : mode;
export default defineConfig({
  testDir: ".", testMatch: "world-character-configuration-api.spec.ts", workers: 1, fullyParallel: false,
  retries: 0, timeout: 180_000, outputDir: `../artifacts/world-character-configuration-api-20261005/${evidence}`,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["json", { outputFile: `../artifacts/world-character-configuration-api-20261005/${evidence}-results.json` }],
    ["junit", { outputFile: `../artifacts/world-character-configuration-api-20261005/${evidence}-results.xml` }]],
  use: { ...devices["Desktop Chrome"], baseURL: process.env.ANGMOO_CHARACTER_PREVIEW_URL ?? "http://127.0.0.1:3339",
    locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: mode }],
});
