import type { Page, Route, TestInfo } from "@playwright/test";
import type { WorldRead } from "../frontend/src/features/worlds/types/worlds";
import { uiDWorld } from "./continuity-next-fixture";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter } from "./world-character-management-fixture";

export function introductionWorld(id = FEED_WORLD): WorldRead {
  return {
    id, slug: id, name: id === FEED_WORLD ? "SNS" : "Other World", tagline: "원래 저장된 한 줄 소개 · Original tagline",
    setting_description: "원래 저장된 World 설명 첫 문단.\n\nOriginal second paragraph, with preserved case and line breaks.",
    daily_life_description: "Original daily life\n두 번째 줄도 보존합니다.",
    genre_tags: ["현대 일상", "Slice of Life"], tone_tags: ["따뜻한", "Quiet"],
    timezone: "Asia/Seoul", language: "ko", visibility: "public", join_policy: "open",
    additional_generation_guidance: "Original guidance: follow the saved setting.",
    places: [
      { key: "park", name: "먼저 저장된 공원", description: "Original park description", available_dayparts: [], access_role_keys: [] },
      { key: "cafe", name: "Second Café", description: "원래 카페 설명", available_dayparts: [], access_role_keys: [] },
    ],
    roles: [{ key: "resident", name: "거주자", description: "Original role description", responsibilities: ["Original responsibility"], allowed_activity_scope: [], autonomous_allowed: true }],
    daypart_profiles: [], rules: [], glossary: [], banner_media_id: null, banner_alt_text: "Saved banner description",
    status: "published", definition_version: 1, row_version: 1, contract_version: "world-v1", contract_hash: "synthetic",
    readiness_status: "publish_ready", created_at: "2026-10-07T00:00:00Z", updated_at: "2026-10-07T00:00:00Z", archived_at: null,
  };
}

export async function installIntroductionFixture(page: Page, info: TestInfo, language: "ko" | "en" = "ko") {
  const fixture = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  const state = {
    worlds: new Map([FEED_WORLD, OTHER_FEED_WORLD].map(id => [id, introductionWorld(id)])),
    profiles: new Map([FEED_WORLD, OTHER_FEED_WORLD].map(world => [world, [
      ...Array.from({ length: 7 }, (_, i) => ({ ...syntheticWorldCharacter(`intro-${i}`, world).profile, display_name: `Original Character ${i + 1}`, avatar_url: "/api/v1/media/assets/synthetic-avatar/content" })),
      syntheticWorldCharacter(ownerId(world), world).profile,
    ]])),
    role: "owner" as "owner" | "editor" | "member", worldFailure: 0, profilesFailure: 0, corruptProfiles: false,
    worldBarrier: null as Promise<void> | null, profilesBarrier: null as Promise<void> | null,
    reads: [] as string[], writes: [] as string[], mediaFailure: false,
  };
  const handler = async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    const world = path.match(/^\/worlds\/([^/]+)$/);
    const profiles = path.match(/^\/worlds\/([^/]+)\/world-characters$/);
    const app = path.match(/^\/worlds\/mine\/([^/]+)$/);
    if (!world && !profiles && !app) return route.fallback();
    if (request.method() !== "GET") { state.writes.push(path); return route.fulfill({ status: 405, json: { detail: "read_only_fixture" } }); }
    state.reads.push(path);
    if (app) return route.fulfill({ json: { schema_version: "local-world-app-v1", surface: "world_app", world: { ...uiDWorld(app[1]), membership_role: state.role } } });
    if (world) {
      const snapshot = structuredClone(state.worlds.get(world[1]));
      if (world[1] === FEED_WORLD && state.worldBarrier) await state.worldBarrier;
      return route.fulfill({ status: state.worldFailure || (snapshot ? 200 : 404), json: state.worldFailure ? { detail: "world_access_forbidden" } : snapshot ?? { detail: "world_not_found" } });
    }
    if (profiles) {
      const items = structuredClone(state.profiles.get(profiles[1]) ?? []);
      if (profiles[1] === FEED_WORLD && state.profilesBarrier) await state.profilesBarrier;
      return route.fulfill({ status: state.profilesFailure || 200, json: state.profilesFailure ? { detail: "world_access_forbidden" } : { schema_version: "world-character-profile-list-v1", world_id: state.corruptProfiles ? "wrong-world" : profiles[1], items } });
    }
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  await page.route("**/media/intro-banner.svg", route => state.mediaFailure
    ? route.fulfill({ status: 404, body: "missing" })
    : route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="280"><rect width="960" height="280" fill="lightblue"/></svg>' }));
  return { ...fixture, state };
}
