import { defineConfig } from "@playwright/test";
import base from "./playwright.static.config";
export default defineConfig({ ...base, testMatch: "refactor-lifecycle.spec.ts" });
