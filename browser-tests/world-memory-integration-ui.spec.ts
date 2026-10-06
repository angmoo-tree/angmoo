import { expect, test } from "@playwright/test";
import { installWorldCharacterManagementFixture, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD, OTHER_FEED_WORLD } from "./world-feed-fixture";

const headings = {
  ko: ["캐릭터 페르소나 설정", "활동 설정", "캐릭터 활동 API key", "SNS 게시글 이미지 생성", "채팅용 API key", "SNS·Chat 이미지 인식 API key", "캐릭터 관심 주제", "활동 방식과 현재 상태", "오늘 하루 계획", "캐릭터 삭제"],
  en: ["Character persona settings", "Activity settings", "Character activity API key", "SNS post image generation", "Chat API key", "SNS and Chat image recognition API key", "Character interests", "Activity mode and current state", "Today's plan", "Delete character"],
};

for (const language of ["ko", "en"] as const) {
  for (const width of [390, 480, 960]) {
    test(`World ten cards, independent edited-field save and navigation draft (${language}, ${width})`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 });
      const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
      const other = structuredClone(state.management.worlds.get(OTHER_FEED_WORLD));
      await page.goto(`${worldCharacterRoute()}?view=settings`);
      const surface = page.locator("[data-world-character-management]"), settings = surface.locator("[data-world-character-settings-form]");
      await expect(settings.locator("section > header > div > h2")).toHaveText(headings[language]);
      expect(state.management.writes).toHaveLength(0); expect(state.management.providerCalls).toEqual([]);
      const persona = settings.locator('[data-world-character-settings-card="persona"]');
      await persona.locator('textarea[name="worldview"]').fill("Original description edited without translation");
      await surface.getByRole("tab", { name: language === "ko" ? "프로필" : "Profile", exact: true }).click();
      await surface.getByRole("tab", { name: language === "ko" ? "설정" : "Settings", exact: true }).click();
      await expect(persona.locator('textarea[name="worldview"]')).toHaveValue("Original description edited without translation");
      await persona.getByRole("button", { name: language === "ko" ? "설정 저장" : "Save settings", exact: true }).click();
      await expect(persona.getByRole("status")).toContainText(language === "ko" ? "저장했어요" : "Saved");
      const write = state.management.writes.find(value => value.path.endsWith("/settings"))!;
      expect(write.body.settings).toEqual({ worldview: "Original description edited without translation" });
      expect(state.management.worlds.get(OTHER_FEED_WORLD)).toEqual(other);
      await expect(settings.getByRole("heading", { name: /캐릭터 설정집|Character lorebook|홍보 활용|Promotion usage/ })).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      for (const card of await settings.locator("section").all()) {
        const icon = card.locator(":scope > header > span");
        if (await icon.count()) expect(await icon.evaluate(node => Math.round(node.getBoundingClientRect().width))).toBe(40);
      }
      for (const button of await settings.getByRole("button").all()) {
        if (await button.isVisible()) expect((await button.boundingBox())!.height, (await button.getAttribute("aria-label")) ?? (await button.textContent()) ?? "button").toBeGreaterThanOrEqual(44);
      }
      expect(state.management.providerCalls).toEqual([]);
      await page.screenshot({ path: info.outputPath(`world-settings-${language}-${width}.png`), fullPage: true });
    });
  }

  test(`World status actual state, description first, three supported actions and sticky header (${language})`, async ({ page }, info) => {
    await page.setViewportSize({ width: 480, height: 850 });
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(`${worldCharacterRoute()}?view=status`);
    const surface = page.locator("[data-world-character-management]"), panel = surface.getByRole("tabpanel");
    await expect(panel.getByRole("heading", { name: language === "ko" ? "캐릭터 페르소나" : "Character persona", exact: true })).toBeVisible();
    const labels = await panel.locator("article h3").allTextContents();
    expect(labels.indexOf(language === "ko" ? "캐릭터 설명" : "Character description")).toBeLessThan(labels.indexOf(language === "ko" ? "성격" : "Personality"));
    await expect(panel).not.toContainText(/리포스트|언팔로우|repost|unfollow/i);
    await expect(panel).toContainText("Original activity title");
    await expect(panel.getByRole("link", { name: language === "ko" ? "게시글 열기" : "Open post", exact: true })).toHaveAttribute("href", `/worlds/${FEED_WORLD}/posts/synthetic-root${info.project.name === "static-export" ? "/" : ""}`);
    const header = surface.locator(":scope > div > header").first();
    const initial = (await header.boundingBox())!.y;
    await page.mouse.wheel(0, 1100);
    await expect.poll(async () => Math.round((await header.boundingBox())!.y)).toBe(Math.round(initial));
    await expect(header.getByRole("button", { name: /뒤로|Back|새로고침|Refresh/ })).toHaveCount(0);
    expect(state.management.writes).toEqual([]); expect(state.management.providerCalls).toEqual([]);
    await page.screenshot({ path: info.outputPath(`world-status-${language}.png`), fullPage: true });
  });
}

test("Own direct key models, new caps, responsive 200-percent text and no AI on ordinary save", async ({ page }, info) => {
  await page.setViewportSize({ width: 960, height: 1000 });
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const settings = page.locator("[data-world-character-settings-form]");
  const vision = settings.locator("section").filter({ has: page.getByRole("heading", { name: "SNS·Chat 이미지 인식 API key", exact: true }) });
  await expect(vision.getByLabel("Google AI 모델", { exact: true })).toHaveValue("google:gemini-3.1-flash-lite:medium");
  await expect(vision.getByLabel("캐릭터 일일 인식 상한", { exact: true })).toHaveValue("10");
  await expect(settings.getByLabel("캐릭터 일일 생성 상한", { exact: true })).toHaveValue("20");
  const options = vision.getByLabel("Google AI 모델", { exact: true }).locator("option");
  await expect(options).toHaveText(["Gemini 3.5 Flash-Lite (high)", "Gemini 3.5 Flash-Lite (medium)", "Gemini 3.1 Flash-Lite (high)", "Gemini 3.1 Flash-Lite (medium)"]);
  await expect(vision.locator('input[type="password"]')).toHaveCount(1);
  await expect(vision.getByRole("combobox")).toHaveCount(1);
  await vision.getByLabel("새 API key", { exact: true }).fill("synthetic-vision-input-only");
  await vision.getByRole("button", { name: "모델 저장", exact: true }).click();
  await expect(vision.getByRole("status").filter({ hasText: "설정을 저장했어요." })).toHaveCount(1);
  await expect(vision.getByLabel("새 API key", { exact: true })).toHaveValue("");
  expect(state.management.writes).toHaveLength(1);
  expect(state.management.writes[0].path).toContain(`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/credentials/vision`);
  expect(state.management.providerCalls).toEqual([]);
  await page.evaluate(() => document.documentElement.style.fontSize = "200%");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await expect(settings.getByRole("heading", { name: "캐릭터 삭제", exact: true })).toHaveCount(1);
  await page.screenshot({ path: info.outputPath("world-settings-200-percent.png"), fullPage: true });
});
