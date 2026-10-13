import { test } from "@playwright/test";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
test("record directory header baseline", async ({ page }, info) => {
  await installIntegrationFixture(page, false, String(info.project.use.baseURL));
  await page.goto(`/worlds/${FEED_WORLD}/characters`);
  const heading = page.locator('[data-world-character-surface="list"] header h2');
  await heading.waitFor();
  console.log("DIRECTORY_BASELINE", await heading.evaluate(element => {
    const value = getComputedStyle(element);
    return Object.fromEntries(["fontFamily", "fontSize", "fontWeight", "lineHeight", "marginTop"].map(key => [key, value[key as keyof CSSStyleDeclaration]]));
  }));
});
