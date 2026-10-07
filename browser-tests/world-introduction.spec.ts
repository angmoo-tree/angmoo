import { test, expect } from "@playwright/test";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installIntroductionFixture } from "./world-introduction-fixture";
import type { Locator } from "@playwright/test";

const routeHref = (path: string) => new RegExp(`^${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/?$`);
async function expectImageLoaded(image: Locator) {
  await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
}

for (const language of ["ko", "en"] as const) {
  test(`World introduction preserves original content, tags, navigation and responsive structure (${language})`, async ({ page }, info) => {
    const fixture = await installIntroductionFixture(page, info, language);
    const world = fixture.state.worlds.get(FEED_WORLD)!;
    await page.goto(`/worlds/${FEED_WORLD}`);
    const intro = page.locator("[data-world-introduction]");
    const preview = intro.locator("[data-world-character-preview]");
    await expect(intro.getByRole("heading", { name: "SNS", exact: true })).toBeVisible();
    await expect(preview.locator("[data-world-character-preview-list] > li")).toHaveCount(7);
    await expect(intro.locator("[data-world-tags] [role=listitem]")).toHaveText([...world.genre_tags, ...world.tone_tags]);
    await expect(intro.locator('[data-world-tag-kind="genre"]').first()).toHaveAttribute("aria-label", `${language === "ko" ? "장르 태그" : "Genre tag"}: 현대 일상`);
    await expect(intro.locator('[data-world-tag-kind="mood"]').last()).toHaveAttribute("aria-label", `${language === "ko" ? "분위기 태그" : "Mood tag"}: Quiet`);
    const nav = page.getByRole("navigation", { name: language === "ko" ? "World 앱 기능" : "World app navigation" });
    await expect(nav.getByRole("link")).toHaveText(language === "ko" ? ["World", "피드", "채팅", "캐릭터", "관계"] : ["World", "Feed", "Chat", "Characters", "Relationships"]);
    await expect(nav.getByRole("link", { name: "World", exact: true })).toHaveAttribute("href", `/worlds/${FEED_WORLD}`);
    const home = page.getByRole("link", { name: language === "ko" ? "디바이스 홈으로 이동" : "Go to Device Home", exact: true });
    await expect(home).toHaveAttribute("href", "/");
    const homeBox = await home.boundingBox(); expect(homeBox!.width).toBe(44); expect(homeBox!.height).toBe(44);
    await expect(home).toHaveText("");
    await expect(preview.getByRole("link", { name: language === "ko" ? "전체 보기" : "View all" })).toHaveAttribute("href", routeHref(`/worlds/${FEED_WORLD}/characters`));
    await expect(preview.getByRole("link", { name: "Original Character 1", exact: true })).toHaveAttribute("href", routeHref(`/worlds/${FEED_WORLD}/characters/intro-0`));
    await expect(preview.getByRole("link", { name: "Synthetic World User", exact: true })).toHaveCount(0);
    await expect(intro.getByRole("link", { name: new RegExp(language === "ko" ? "이 World의 내 프로필" : "My Profile in this World") })).toHaveAttribute("href", routeHref(`/worlds/${FEED_WORLD}/characters/${ownerId()}`));
    await expectImageLoaded(intro.locator("[data-world-banner] img"));

    for (const width of [320, 390, 480, 960]) {
      await page.setViewportSize({ width, height: 1000 });
      const geometry = await intro.evaluate(root => {
        const bounds = (query: string) => root.querySelector(query)!.getBoundingClientRect();
        return { viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth,
          tags: bounds("[data-world-tags]").y, titleBottom: bounds("h1").bottom, tagline: bounds("[data-world-tagline]").y,
          tagsBottom: bounds("[data-world-tags]").bottom, bannerHeight: bounds("[data-world-banner]").height,
          avatarWidth: bounds("[data-world-character-preview-list] img").width,
          nextAvatarPeeks: Array.from(root.querySelectorAll("[data-world-character-preview-list] img")).some(image => {
            const imageBounds = image.getBoundingClientRect(), listBounds = bounds("[data-world-character-preview-list]");
            return imageBounds.left < listBounds.right - 1 && imageBounds.right > listBounds.right + 1;
          }),
          verticalScrollers: Array.from(root.querySelectorAll("*" )).filter(el => ["auto", "scroll"].includes(getComputedStyle(el).overflowY) && el.scrollHeight > el.clientHeight + 1).length };
      });
      expect(geometry.document).toBeLessThanOrEqual(geometry.viewport);
      expect(geometry.tags).toBeGreaterThan(geometry.titleBottom); expect(geometry.tagline).toBeGreaterThan(geometry.tagsBottom);
      expect(geometry.bannerHeight).toBeGreaterThanOrEqual(160); expect(geometry.bannerHeight).toBeLessThanOrEqual(280);
      expect(geometry.avatarWidth).toBeGreaterThanOrEqual(72); expect(geometry.avatarWidth).toBeLessThanOrEqual(88);
      if (width < 640) expect(geometry.nextAvatarPeeks).toBe(true);
      expect(geometry.verticalScrollers).toBe(0);
    }
    const more = intro.getByRole("button", { name: language === "ko" ? "더 보기" : "Read more", exact: true });
    await expect(more).toHaveAttribute("aria-expanded", "false");
    await more.click();
    await expect(intro.locator("[data-world-description]")).toHaveText(world.setting_description);
    await expect(intro.locator("[data-world-about-details] h3")).toHaveText(language === "ko" ? ["일상", "장소", "역할·직업", "추가 생성 지침"] : ["Daily life", "Locations", "Roles & occupations", "Additional generation guidance"]);
    await expect(intro.locator("[data-world-about-details] h4")).toHaveText(["먼저 저장된 공원", "Second Café", "거주자"]);
    await expect(intro.locator("[data-world-about-details]")).toContainText(world.daily_life_description);
    const less = intro.getByRole("button", { name: language === "ko" ? "접기" : "Show less", exact: true });
    await expect(less).toHaveAttribute("aria-expanded", "true");
    await expect(intro.locator(`[id="${await less.getAttribute("aria-controls")}"]`)).toHaveCount(1);
    await less.click(); await expect(intro.locator("[data-world-about-details]")).toHaveCount(0);
    expect(fixture.state.writes).toEqual([]); expect(fixture.management.writes).toEqual([]); expect(fixture.base.base.providerCalls).toEqual([]);
  });

  test(`World introduction distinguishes absent, failed and registered banners without changing data (${language})`, async ({ page }, info) => {
    const fixture = await installIntroductionFixture(page, info, language);
    const world = fixture.state.worlds.get(FEED_WORLD)!;
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(`/worlds/${FEED_WORLD}`);
    const banner = page.locator("[data-world-banner]");
    await expect(banner).toHaveAttribute("data-world-banner", "default");
    const height = (await banner.boundingBox())!.height;
    await expect(banner.getByRole("img")).toHaveAttribute("alt", language === "ko" ? "World 기본 배너" : "Default World banner");
    await expectImageLoaded(banner.getByRole("img"));
    world.banner_media_id = "/media/intro-banner.svg";
    await page.reload(); await expect(banner).toHaveAttribute("data-world-banner", "registered");
    await expect(banner.getByRole("img")).toHaveAttribute("alt", world.banner_alt_text);
    await expectImageLoaded(banner.getByRole("img"));
    expect((await banner.boundingBox())!.height).toBe(height);
    fixture.state.mediaFailure = true;
    await page.reload();
    await expect.poll(async () => new URL((await banner.getByRole("img").getAttribute("src"))!, String(info.project.use.baseURL)).pathname).toBe("/world-default-banner.svg");
    await expect(banner).toHaveAttribute("data-world-banner", "default");
    await expectImageLoaded(banner.getByRole("img"));
    expect((await banner.boundingBox())!.height).toBe(height);
    expect(fixture.state.worlds.get(FEED_WORLD)!.banner_media_id).toBe("/media/intro-banner.svg");
    expect(fixture.state.writes).toEqual([]); expect(fixture.base.base.providerCalls).toEqual([]);
  });
}

test("genre and mood tags wrap unchanged; either group or both groups can be empty", async ({ page }, info) => {
  const fixture = await installIntroductionFixture(page, info);
  const world = fixture.state.worlds.get(FEED_WORLD)!;
  for (const [genres, moods] of [[['OnlyGenre'], []], [[], ['OnlyMood']], [[], []], [['A'.repeat(120), 'Original Case'], ['긴 분위기 '.repeat(20)]]] as [string[], string[]][]) {
    world.genre_tags = genres; world.tone_tags = moods;
    await page.setViewportSize({ width: 320, height: 900 }); await page.goto(`/worlds/${FEED_WORLD}`);
    await expect(page.locator("[data-world-about]")).toBeVisible();
    const tags = page.locator("[data-world-tags]");
    if (genres.length || moods.length) await expect(tags.locator("[role=listitem]")).toHaveText([...genres, ...moods]);
    else await expect(tags).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
});

test("short introduction needs no toggle; long introduction exposes all four empty detail messages", async ({ page }, info) => {
  const fixture = await installIntroductionFixture(page, info);
  const world = fixture.state.worlds.get(FEED_WORLD)!;
  Object.assign(world, { setting_description: "Short original description", daily_life_description: "", places: [], roles: [], additional_generation_guidance: "" });
  await page.goto(`/worlds/${FEED_WORLD}`); await expect(page.locator("[data-world-about]")).toBeVisible();
  await expect(page.getByRole("button", { name: "더 보기", exact: true })).toHaveCount(0);
  world.setting_description = "Original long description with original line breaks.\n".repeat(20);
  await page.reload(); await page.getByRole("button", { name: "더 보기", exact: true }).click();
  await expect(page.locator("[data-world-description]")).toHaveText(world.setting_description);
  for (const message of ["작성된 일상 설명이 없어요.", "등록된 장소가 없어요.", "등록된 역할·직업이 없어요.", "작성된 추가 생성 지침이 없어요."]) await expect(page.getByText(message, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "접기", exact: true }).click();
  await expect(page.getByRole("button", { name: "더 보기", exact: true })).toBeVisible();
});

test("character preview keeps authorized empty, error, retry and full keyboard list separate", async ({ page }, info) => {
  const fixture = await installIntroductionFixture(page, info);
  const owner = fixture.state.profiles.get(FEED_WORLD)!.at(-1)!;
  fixture.state.profiles.set(FEED_WORLD, [owner]);
  await page.goto(`/worlds/${FEED_WORLD}`);
  const preview = page.locator("[data-world-character-preview]");
  await expect(preview.getByText("이 World에 참여 중인 자율 캐릭터가 없어요.", { exact: true })).toBeVisible();
  await expect(preview.getByRole("link", { name: "캐릭터 추가", exact: true })).toHaveAttribute("href", routeHref(`/studio/worlds/${FEED_WORLD}`));
  fixture.state.role = "member";
  await page.reload(); await expect(preview.getByText("이 World에 참여 중인 자율 캐릭터가 없어요.", { exact: true })).toBeVisible();
  await expect(preview.getByRole("link", { name: "캐릭터 추가", exact: true })).toHaveCount(0);
  fixture.state.profilesFailure = 403;
  await page.reload(); await expect(preview.getByText("캐릭터를 불러오지 못했어요.", { exact: true })).toBeVisible();
  await expect(preview.getByText("이 World에 참여 중인 자율 캐릭터가 없어요.", { exact: true })).toHaveCount(0);
  fixture.state.profilesFailure = 0;
  fixture.state.profiles.set(FEED_WORLD, Array.from({ length: 21 }, (_, i) => ({ ...owner, control_mode: "autonomous", world_character_id: `many-${i}`, character_id: `many-character-${i}`, display_name: `Full original very long character name ${i}` })));
  await preview.getByRole("button", { name: "다시 시도", exact: true }).click();
  const list = preview.locator("[data-world-character-preview-list]");
  await expect(list.getByRole("link")).toHaveCount(21);
  await list.getByRole("link").first().focus();
  for (let i = 1; i < 21; i++) await page.keyboard.press("Tab");
  await expect(list.getByRole("link").last()).toBeFocused();
  expect(await list.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  await expect(list.getByRole("link").last()).toHaveAttribute("aria-label", "Full original very long character name 20");
  fixture.state.corruptProfiles = true;
  await page.reload(); await expect(preview.getByText("캐릭터를 불러오지 못했어요.", { exact: true })).toBeVisible();
  await expect(list).toHaveCount(0);
  expect(fixture.state.writes).toEqual([]); expect(fixture.management.writes).toEqual([]);
});

test("World detail rejects forbidden or mismatched reads before exposing definition or profiles", async ({ page }, info) => {
  const fixture = await installIntroductionFixture(page, info);
  fixture.state.worldFailure = 403;
  await page.goto(`/worlds/${FEED_WORLD}`);
  await expect(page.getByText("World 소개를 불러오지 못했어요. 접근 권한과 연결 상태를 확인해주세요.", { exact: true })).toBeVisible();
  expect(fixture.state.reads.some(path => path.endsWith("/world-characters"))).toBe(false);
  await expect(page.locator("[data-world-about]")).toHaveCount(0);
  fixture.state.worldFailure = 0; fixture.state.worlds.get(FEED_WORLD)!.id = "forged-world";
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByText("World 소개를 불러오지 못했어요. 접근 권한과 연결 상태를 확인해주세요.", { exact: true })).toBeVisible();
  await expect(page.locator("[data-world-tags]")).toHaveCount(0);
  fixture.state.worlds.get(FEED_WORLD)!.id = FEED_WORLD;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.locator("[data-world-about]")).toBeVisible();
});

test("delayed definition and character responses cannot cross World navigation", async ({ page }, info) => {
  const fixture = await installIntroductionFixture(page, info);
  let release!: () => void;
  fixture.state.worldBarrier = new Promise<void>(resolve => { release = resolve; });
  fixture.state.worlds.get(FEED_WORLD)!.setting_description = "Private previous World definition";
  await page.goto(`/worlds/${FEED_WORLD}`);
  await expect.poll(() => fixture.state.reads.includes(`/worlds/${FEED_WORLD}`)).toBe(true);
  await page.goto(`/worlds/${OTHER_FEED_WORLD}`);
  await expect(page.getByRole("heading", { name: "Other World", exact: true })).toBeVisible();
  release(); await expect(page.getByText("Private previous World definition", { exact: true })).toHaveCount(0);
  await expect(page.locator("[data-world-character-preview-list] a").first()).toHaveAttribute("href", routeHref(`/worlds/${OTHER_FEED_WORLD}/characters/intro-0`));
  fixture.state.worldBarrier = null;
  fixture.state.profilesBarrier = new Promise<void>(resolve => { release = resolve; });
  fixture.state.profiles.get(FEED_WORLD)![0].display_name = "Private previous World character";
  await page.goto(`/worlds/${FEED_WORLD}`);
  await expect.poll(() => fixture.state.reads.includes(`/worlds/${FEED_WORLD}/world-characters`)).toBe(true);
  await page.goto(`/worlds/${OTHER_FEED_WORLD}`);
  await expect(page.getByRole("heading", { name: "Other World", exact: true })).toBeVisible();
  release(); await expect(page.getByText("Private previous World character", { exact: true })).toHaveCount(0);
  expect(fixture.state.writes).toEqual([]); expect(fixture.base.base.providerCalls).toEqual([]);
});

for (const scope of ["session", "runtime"] as const) {
  test(`revoked ${scope} scope removes introduction data and rejects its pending response`, async ({ page }, info) => {
    const fixture = await installIntroductionFixture(page, info);
    fixture.state.worlds.get(FEED_WORLD)!.setting_description = "Private previous introduction";
    fixture.state.profiles.get(FEED_WORLD)![0].display_name = "Private previous character";
    let release!: () => void;
    const barrier = new Promise<void>(resolve => { release = resolve; });
    if (scope === "session") fixture.state.worldBarrier = barrier;
    else fixture.state.profilesBarrier = barrier;
    await page.goto(`/worlds/${FEED_WORLD}`);
    await expect.poll(() => fixture.state.reads.includes(`/worlds/${FEED_WORLD}${scope === "runtime" ? "/world-characters" : ""}`)).toBe(true);
    if (scope === "runtime") await expect(page.getByText("Private previous introduction", { exact: true })).toBeVisible();
    fixture.state.worldBarrier = null; fixture.state.profilesBarrier = null; fixture.state.worldFailure = 403;
    if (scope === "session") fixture.management.authOwner = "replacement-owner";
    await page.evaluate(event => window.dispatchEvent(new Event(event)), scope === "session" ? "angmoo:auth-changed" : "angmoo:desktop-runtime-config-changed");
    await expect(page.getByText("World 소개를 불러오지 못했어요. 접근 권한과 연결 상태를 확인해주세요.", { exact: true })).toBeVisible();
    release();
    await expect(page.getByText("Private previous introduction", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Private previous character", { exact: true })).toHaveCount(0);
    await expect(page.locator("[data-world-character-preview]")).toHaveCount(0);
    expect(fixture.state.writes).toEqual([]); expect(fixture.management.writes).toEqual([]);
  });
}
