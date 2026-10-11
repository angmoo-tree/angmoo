import { defineConfig } from "@playwright/test";
import base from "./playwright.creator-copy.config";
export default defineConfig({ ...base,
  testMatch: ["creator-copy-ui.spec.ts", "creator-copy-state.spec.ts", "creator-copy-media.spec.ts", "local-creator.spec.ts", "chat-memory-world-copy.spec.ts"],
  outputDir: "../artifacts/chat-memory-world-20261011/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/chat-memory-world-20261011/browser-results.json" }]],
  projects: [
    { name: "next", use: { baseURL: "http://127.0.0.1:3380" } },
    { name: "static-export", use: { baseURL: "http://127.0.0.1:3385" } },
  ],
});
