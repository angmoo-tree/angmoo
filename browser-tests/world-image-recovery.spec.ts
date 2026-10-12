import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { uiDOwnerActor } from "./continuity-next-fixture";

async function fixture(page: Page, staticShell: boolean, baseURL: string, language: "ko" | "en") {
  await installIntegrationFixture(page, staticShell, baseURL, language);
  const world = {
    id: FEED_WORLD, slug: "image-world", name: "Image World", tagline: "Synthetic image recovery",
    setting_description: "A small synthetic town.", daily_life_description: "Synthetic daily life.", genre_tags: [], tone_tags: [],
    timezone: "Asia/Seoul", language, visibility: "private", join_policy: "private", additional_generation_guidance: "",
    places: [], roles: [], daypart_profiles: [], rules: [], glossary: [], banner_media_id: null as string | null,
    icon_media_id: null as string | null, banner_alt_text: "", status: "draft", definition_version: 1, row_version: 1,
    contract_version: "world-v1", contract_hash: "a".repeat(64), readiness_status: "publish_ready",
    created_at: "2026-10-12T00:00:00Z", updated_at: "2026-10-12T00:00:00Z", archived_at: null,
  };
  const identity = { ...uiDOwnerActor(FEED_WORLD), version: 1,
    profile: { ...uiDOwnerActor(FEED_WORLD).profile, handle: "image_user", avatar_url: null as string | null, banner_url: null as string | null } };
  const context = () => ({ world, membership_role: "owner", readiness: { world_id: world.id, definition_version: 1, row_version: world.row_version,
    contract_version: world.contract_version, contract_hash: world.contract_hash, required_fields: {}, optional_setting_count: 0,
    quality_tier: "CORE", issues: [], ready_for_publish: true, evaluated_at: world.updated_at } });
  const state = { world, identity, images: new Map<string, Buffer>(), writes: [] as Record<string, unknown>[], reads: [] as string[], authorized: true };
  const handler = async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    if (path === `/worlds/${FEED_WORLD}/creator-context`) return route.fulfill({ json: context() });
    if (path === `/worlds/${FEED_WORLD}/my-profile/ensure`) return route.fulfill({ json: identity });
    if (path === `/worlds/${FEED_WORLD}/my-profile/media` && method === "POST") {
      const body = request.postDataJSON();
      expect(Object.keys(body).sort()).toEqual(["content_type", "data_base64", "media_type", "version"]);
      expect(body.version).toBe(identity.version);
      const kind = body.media_type as "avatar" | "banner", name = `${kind}-fixture-${identity.version}.webp`;
      state.images.set(name, Buffer.from(body.data_base64, "base64"));
      identity.profile[`${kind}_url`] = `/media/characters/profile-owner/${name}`;
      identity.version++; state.writes.push(body);
      return route.fulfill({ json: identity });
    }
    if (/\/(icon|banner)$/.test(path) && method === "POST") {
      const body = request.postDataJSON(); expect(body.row_version).toBe(world.row_version);
      const kind = path.endsWith("/icon") ? "icon" : "banner", name = `${kind}-fixture-${world.row_version}.webp`;
      state.images.set(name, Buffer.from(body.data_base64, "base64"));
      world[`${kind}_media_id`] = `/media/worlds/${FEED_WORLD}/${name}`;
      world.row_version++; state.writes.push(body);
      return route.fulfill({ json: context() });
    }
    if (path.startsWith(`/worlds/${FEED_WORLD}/media/`)) {
      state.reads.push(path);
      const content = state.images.get(path.split("/").at(-1)!);
      return state.authorized && content ? route.fulfill({ contentType: "image/webp", body: content }) : route.fulfill({ status: 404 });
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  await page.route("**/media/characters/profile-owner/**", route => {
    const content = state.images.get(new URL(route.request().url()).pathname.split("/").at(-1)!);
    return content ? route.fulfill({ contentType: "image/webp", body: content }) : route.fulfill({ status: 404 });
  });
  return state;
}

for (const language of ["ko", "en"] as const) {
  test(`four stored images survive apply and reload with exact API contracts ${language}`, async ({ page }, info) => {
    const state = await fixture(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    const worldCatalog = JSON.parse(readFileSync(`../frontend/src/features/worlds/locales/${language}.json`, "utf8"));
    const catalog = { ...worldCatalog,
      ...JSON.parse(readFileSync(`../frontend/src/features/characters/locales/${language}.json`, "utf8")) };
    const text = (value: string) => catalog[value] ?? value;
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const profile = page.getByRole("region", { name: worldCatalog["내 프로필 편집"], exact: true });
    const previews = page.locator("[data-world-image-previews]");
    const photo = Buffer.from(await page.evaluate(() => {
      const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 160;
      const context = canvas.getContext("2d")!; context.fillStyle = "#416781"; context.fillRect(0, 0, 320, 160);
      return canvas.toDataURL("image/png").split(",")[1];
    }), "base64");
    const url = page.url();
    const worldName = page.getByLabel(new RegExp(`^${text("World 이름")}`)).last();
    await worldName.fill("Unsaved World image draft");
    for (const [region, button, apply] of [
      [profile, "아바타 업로드", "저장"], [profile, "배너 업로드", "저장"],
      [previews, "아이콘 업로드", "적용"], [previews, "배너 업로드", "적용"],
    ] as const) {
      const chosen = page.waitForEvent("filechooser");
      await region.getByRole("button", { name: text(button), exact: true }).click();
      await (await chosen).setFiles({ name: "fixture.png", mimeType: "image/png", buffer: photo });
      await page.getByRole("dialog").getByRole("button", { name: text(apply), exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page).toHaveURL(url);
      await expect(worldName).toHaveValue("Unsaved World image draft");
    }
    async function checkImages() {
      await expect(profile.locator("img")).toHaveCount(2);
      await expect(previews.locator("img")).toHaveCount(2);
      for (const region of [profile, previews]) {
        await expect.poll(() => region.locator("img").evaluateAll(images => images.map(image =>
          `${(image as HTMLImageElement).naturalWidth}x${(image as HTMLImageElement).naturalHeight}`,
        ).sort())).toEqual(["1024x384", "768x768"]);
      }
    }
    await checkImages();
    expect(state.writes).toHaveLength(4);
    expect(state.world.icon_media_id).toMatch(/^\/media\/worlds\//);
    expect(state.world.banner_media_id).toMatch(/^\/media\/worlds\//);
    expect(state.reads.some(path => path.includes("/media/icon-"))).toBe(true);
    expect(state.reads.some(path => path.includes("/media/banner-"))).toBe(true);
    await page.reload(); await checkImages();
    const profileMedia = profile.locator(".overflow-hidden").first();
    await profileMedia.scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath(`profile-images-${language}.png`), clip: (await profileMedia.boundingBox())! });
    await previews.scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath(`world-images-${language}.png`), clip: (await previews.boundingBox())! });
    state.authorized = false;
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
    await expect(previews.locator("[data-world-banner]")).toHaveAttribute("data-world-banner", "default");
    expect(state.writes).toHaveLength(4);
  });
}
