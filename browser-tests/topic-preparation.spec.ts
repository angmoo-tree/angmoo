import { test, expect, type Page, type TestInfo, type Route } from "@playwright/test";
import { installUiFixture } from "./world-ui-improvements-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT, worldCharacterRoute } from "./world-character-management-fixture";

async function fixture(page: Page, info: TestInfo, language: "ko" | "en", hasKey = true) {
  const state = await installUiFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  const credentialKey = `${FEED_WORLD}:${WORLD_AGENT}:sns`;
  if (hasKey) state.management.credentials.set(credentialKey, { purpose: "sns", provider: "google",
    model: "gemini-3.5-flash-lite", thinking_level: "medium", has_key: true, fingerprint: "synthetic", revision: 1 });
  const commands: string[] = [];
  let failed = false;
  const handler = async (route: Route) => {
    const request = route.request(), url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/(backend|v1)/, "");
    if (!path.match(/\/recommendation-topics(?:\/regenerate)?$/)) return route.fallback();
    if (request.method() === "POST") { commands.push(request.postDataJSON().request_id); failed = true; }
    const saved = state.management.credentials.get(credentialKey);
    return route.fulfill({ json: { world_id: FEED_WORLD, world_character_id: WORLD_AGENT, state: failed ? "failed" : "ready",
      topics: state.topics.map((name, i) => ({ id: `topic-${i}`, name, scope: "world" })), key_world_character_id: WORLD_AGENT,
      model: hasKey ? saved?.model : null, thinking_level: hasKey ? saved?.thinking_level : null, has_key: hasKey,
      last_code: failed ? "generation_failed" : null, approval_required: false, recent_deliveries: [], recent_feed: [] } });
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return { state, commands };
}

for (const language of ["ko", "en"] as const) {
  test(`saved activity model, settings navigation and failed regeneration preserve topics (${language})`, async ({ page }, info) => {
    const { state, commands } = await fixture(page, info, language);
    await page.setViewportSize({ width: language === "ko" ? 390 : 1100, height: 900 });
    await page.goto(`${worldCharacterRoute()}?view=settings`);
    const topics = page.getByRole("region", { name: language === "ko" ? "캐릭터 관심 주제" : "Character interests", exact: true });
    const keyCard = page.getByRole("region", { name: language === "ko" ? "캐릭터 활동 API key" : "Character activity API key", exact: true });
    await expect(topics).toContainText("gemini-3.5-flash-lite · thinking medium");
    await expect(topics).toContainText(language === "ko" ? "캐릭터 활동 API key 사용" : "Uses the character activity API key");
    await expect(topics).not.toContainText(language === "ko" ? "일과 생성 키" : "routine-generation key");
    await expect(topics.locator("li")).toHaveCount(10);
    expect(commands).toEqual([]);
    await topics.getByRole("button", { name: language === "ko" ? "캐릭터 활동 API key 설정" : "Character activity API key settings", exact: true }).click();
    await expect(keyCard.locator("..")).toBeFocused();
    await keyCard.getByRole("combobox").selectOption({ label: "Gemini 3.1 Flash-Lite (high)" });
    // Unsaved choices must not change the displayed effective settings.
    await expect(topics).toContainText("gemini-3.5-flash-lite · thinking medium");
    await keyCard.getByRole("button", { name: language === "ko" ? "모델 저장" : "Save model", exact: true }).click();
    await expect(topics).toContainText("gemini-3.1-flash-lite · thinking high");
    await expect(topics.locator("li")).toHaveCount(10);
    expect(commands).toEqual([]);
    await topics.getByRole("button", { name: language === "ko" ? "캐릭터 주제 다시 만들기" : "Regenerate character topics", exact: true }).click();
    await expect(topics.getByRole("status")).toContainText(language === "ko" ? "주제 생성 실패" : "Couldn't prepare interests · Keeping previous results");
    await expect(topics.locator("li")).toHaveText(state.topics);
    expect(commands).toHaveLength(1);
    expect(state.management.providerCalls).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await topics.screenshot({ path: info.outputPath(`topics-${language}.png`) });
  });

  test(`missing activity key displays no invented model (${language})`, async ({ page }, info) => {
    const { commands } = await fixture(page, info, language, false);
    await page.goto(`${worldCharacterRoute()}?view=settings`);
    const topics = page.getByRole("region", { name: language === "ko" ? "캐릭터 관심 주제" : "Character interests", exact: true });
    await expect(topics).toContainText(language === "ko" ? "캐릭터 활동 API key를 먼저 저장해 주세요." : "Save the character activity API key first.");
    await expect(topics).not.toContainText("gemini-");
    await expect(topics.locator("li")).toHaveCount(10);
    expect(commands).toEqual([]);
  });
}
