import { existingLocalSessionRead } from "./fixtures/existing-local-session.mjs";
import { expect, test, type Route } from "@playwright/test";
import { continuityAgentDetail } from "./continuity-fixture";
import { installBackendFixture, json } from "./continuity-next-fixture";
import { VISUAL_ENVIRONMENT } from "./fixtures/visual-environment.mjs";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD, OTHER_FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT } from "./world-character-management-fixture";

const staticShell = process.env.ANGMOO_DAILY_STATIC === "1";
test.use({ locale: "ko-KR", timezoneId: "Asia/Seoul" });

async function environmentFixture(route: Route) {
  expect(["GET", "POST"]).toContain(route.request().method());
  if (route.request().method() === "POST") {
    expect(route.request().postDataJSON()).toMatchObject({
      expected_revision: 1, preferred_language: "ko-KR", timezone: "Asia/Seoul",
    });
  }
  return json(route, VISUAL_ENVIRONMENT);
}
test("agent settings uses daily preparation without legacy analysis and preserves hidden settings", async ({ page }) => {
  if (staticShell) await page.addInitScript(() => Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: {
    profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: "daily-fixture-token-0000000000000",
  } }));
  else await installBackendFixture(page);
  const characterId = "daily-settings";
  const original = continuityAgentDetail(characterId);
  const agent = { ...original, settings: { ...original.settings, allow_repost: true, allow_follow: true, allow_unfollow: true },
    activity_profile_readiness: { ready: true, source: "daily_preparation", world_id: "daily-world", world_character_id: "daily-actor" } };
  const writes: Record<string, unknown>[] = [];
  await page.route(staticShell ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    const localSession = existingLocalSessionRead(new URL(route.request().url()), route.request().method(), { id: "owner", display_name: "Owner" }, {});
    if (localSession !== undefined) return route.fulfill({ json: localSession });
    if (path === "/auth/me") return json(route, { id: "owner", display_name: "Owner", profile_setup_completed: true, is_admin: true, feed_content_filter: "all", ui_language: "ko", ui_preference_revision: 0 });
    if (path === "/auth/local/environment") return environmentFixture(route);
    if (route.request().method() !== "GET") {
      expect(path).toBe(`/agents/${characterId}/settings`);
      writes.push(route.request().postDataJSON());
      return json(route, agent);
    }
    if (path === `/agents/${characterId}`) return json(route, agent);
    if (path.includes("recommendation-topics")) return json(route, { state: "ready", topics: [], recent_deliveries: [], recent_feed: [] });
    if (path.includes("posts")) return json(route, { items: [], next_cursor: null });
    if (path.includes("lore")) return json(route, []);
    if (staticShell) return json(route, {});
    return route.fallback();
  });
  await page.goto(`/agents/${characterId}?tab=settings`);
  await expect(page.getByRole("heading", { name: "오늘 하루 계획과 활동 준비" })).toBeVisible();
  await expect(page.getByRole("button", { name: "성향 분석 실행" })).toHaveCount(0);
  await expect(page.getByText("커뮤니티 성향 분석이 필요합니다.", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "World 활동 준비 확인" })).toHaveAttribute("href", `/characters/${characterId}/worlds/daily-world/autonomy-setup${staticShell ? "/" : ""}`);
  await expect(page.getByRole("checkbox", { name: "리포스트하기", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ allow_repost: true, allow_follow: true, allow_unfollow: true });
});

test("World activity settings remain OFF until explicit activation and preserve scope after a failed attempt", async ({ page }, testInfo) => {
  const state = await installIntegrationFixture(page, staticShell, String(testInfo.project.use.baseURL));
  const actor = state.ui.management.worlds.get(FEED_WORLD)!.find(item => item.profile.world_character_id === WORLD_AGENT)!;
  const other = state.ui.management.worlds.get(OTHER_FEED_WORLD)!.find(item => item.profile.world_character_id === WORLD_AGENT)!;
  const otherEnabled = other.autonomous_enabled;
  state.draftWorld = true;
  const target = `/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/activate`;
  const attempts: { path: string; body: Record<string, unknown> }[] = [];
  await page.route(staticShell ? "http://127.0.0.1:8080/api/v1/**/activate" : "**/api/backend/**/activate", async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    expect(path).toBe(target);expect(route.request().method()).toBe("POST");
    attempts.push({path, body: route.request().postDataJSON()});
    if (attempts.length === 1) return json(route, {detail:"synthetic_activation_unavailable"}, 503);
    return route.fallback();
  });
  await page.setViewportSize({ width: 430, height: 900 });
  await page.goto(`/characters/${actor.profile.character_id}/worlds/${FEED_WORLD}/autonomy-setup`);
  const activity = page.getByRole("region", {name:"활동 설정",exact:true});
  const enable = activity.getByRole("button",{name:"자율활동 켜기",exact:true});
  await expect(activity).toContainText("자율활동 OFF");await expect(enable).toBeDisabled();
  await expect(activity).toContainText("World를 개시한 뒤 자율활동을 켤 수 있어요.");
  expect(state.writes).toEqual([]);expect(state.ui.management.writes).toEqual([]);expect(attempts).toEqual([]);
  state.draftWorld = false;
  state.ui.management.credentials.set(`${FEED_WORLD}:${WORLD_AGENT}:sns`,{provider:"google",model:"gemini-3.1-flash-lite",has_key:true,revision:1,configuration_revision:1});
  await page.reload();await expect(enable).toBeEnabled();expect(attempts).toEqual([]);
  await enable.click();await expect(activity.getByRole("alert")).toContainText("저장하지 못했어요. 입력을 보존했으니 최신 설정을 확인해주세요.");
  await expect(activity).toContainText("자율활동 OFF");await expect(enable).toBeEnabled();
  expect(actor.autonomous_enabled).toBe(false);expect(attempts).toEqual([{path:target,body:{expected_revision:1}}]);
  await enable.click();await expect(activity).toContainText("자율활동 ON");
  expect(attempts).toEqual([{path:target,body:{expected_revision:1}},{path:target,body:{expected_revision:1}}]);
  expect(state.ui.management.writes.filter(item=>item.path.endsWith("/activate"))).toHaveLength(1);
  expect(other.autonomous_enabled).toBe(otherEnabled);expect(state.ui.management.providerCalls).toEqual([]);expect(state.unexpected).toEqual([]);
  await expect(page.getByRole("heading", {name:"오늘 하루 계획",exact:true})).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("daily-preparation.png"), fullPage: true });
});
