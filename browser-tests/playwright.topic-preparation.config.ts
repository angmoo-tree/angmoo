import { defineConfig } from "@playwright/test";
import base from "./playwright.world-ui-improvements.config";

export default defineConfig({
  ...base,
  testMatch: "topic-preparation.spec.ts",
  outputDir: "../artifacts/topic-preparation-20261018/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/topic-preparation-20261018/browser-results.json" }]],
  projects: [
    { name: "next", use: { baseURL: "http://127.0.0.1:3357" } },
    { name: "static-export", use: { baseURL: "http://127.0.0.1:3358" } },
  ],
  webServer: [
    { command: "pnpm --dir ../frontend dev --hostname 127.0.0.1 --port 3357", url: "http://127.0.0.1:3357", timeout: 120_000,
      env: { ANGMOO_NEXT_DIST_DIR: ".next-topic-preparation", NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE: "" } },
    { command: "pnpm --dir ../frontend exec next dev static-shell --hostname 127.0.0.1 --port 3358", url: "http://127.0.0.1:3358", timeout: 120_000,
      env: { NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE: "tauri-static" } },
  ],
});
