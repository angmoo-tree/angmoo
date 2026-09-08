import config from "./playwright.static.config";
export default { ...config, testMatch: ["static-product-shell.spec.ts", "world-continuity-static.spec.ts"] };
