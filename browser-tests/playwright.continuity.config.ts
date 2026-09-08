import config from "./playwright.config";
export default { ...config, testMatch: ["product-shell.spec.ts", "world-continuity.spec.ts"] };
