import { defineConfig } from "@playwright/test";
import original from "./playwright.memory-situation.config";

export default defineConfig({
  ...original, testMatch: ["memory-situation.spec.ts", "memory-situation-recovery.spec.ts"],
  outputDir: "../artifacts/situation-recovery-validation/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/situation-recovery-validation/browser-results.json" }]],
});
