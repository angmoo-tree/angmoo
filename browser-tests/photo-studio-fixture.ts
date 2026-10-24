import { expect, type Page } from "@playwright/test";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";

export async function studio(page: Page, staticShell: boolean, baseURL: string, language: "ko" | "en") {
  const base = await installIntegrationFixture(page, staticShell, baseURL, language);
  const world = { id: FEED_WORLD, slug: "fixture-world", name: "Draft World", tagline: "A small synthetic town",
    setting_description: "A small town where synthetic characters exchange stories.", daily_life_description: "Characters read and share their ordinary days.",
    genre_tags: ["Everyday"], tone_tags: [], timezone: "Asia/Seoul", language: "ko", visibility: "private", join_policy: "private",
    additional_generation_guidance: "", places: [], roles: [] as { key: string; name: string; description: string; responsibilities: string[]; allowed_activity_scope: string[]; autonomous_allowed: boolean }[], daypart_profiles: [], rules: [], glossary: [], banner_media_id: null as string | null, icon_media_id: null as string | null,
    banner_alt_text: "", status: "draft", definition_version: 1, row_version: 1, contract_version: "world-v1", contract_hash: "a".repeat(64),
    readiness_status: "publish_ready", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z", archived_at: null };
  const context = () => ({ world, membership_role: "owner", readiness: { world_id: world.id, definition_version: 1, row_version: world.row_version,
    contract_version: "world-v1", contract_hash: world.contract_hash, required_fields: {}, optional_setting_count: 0, quality_tier: "CORE", issues: [], ready_for_publish: true, evaluated_at: world.updated_at } });
  const state = { world, base, context, writes: [] as { path: string; body: any }[], imageFailure: 0, images: new Map<string, Buffer>() };
  const handler = async (route: any) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    if (path === `/worlds/${FEED_WORLD}/creator-context`) return route.fulfill({ json: context() });
    if (path === `/worlds/${FEED_WORLD}/readiness` || path === `/worlds/${FEED_WORLD}/validate`) return route.fulfill({ json: context().readiness });
    if (path.startsWith(`/worlds/${FEED_WORLD}/media/`) && method === "GET") {
      const name = path.split("/").at(-1)!;
      const image = state.images.get(name);
      return image ? route.fulfill({ contentType: "image/webp", body: image }) : route.fulfill({ status: 404 });
    }
    if ([`/worlds/${FEED_WORLD}`, `/worlds/${FEED_WORLD}/icon`, `/worlds/${FEED_WORLD}/banner`].includes(path) && method !== "GET") {
      const body = request.postDataJSON(); state.writes.push({ path, body }); expect(body.row_version).toBe(world.row_version);
      if (/\/(icon|banner)$/.test(path)) {
        if (state.imageFailure) return route.fulfill({ status: state.imageFailure, json: { detail: "world_row_version_conflict" } });
        const kind = path.endsWith("/icon") ? "icon" : "banner";
        const filename = `${kind}-fixture-${world.row_version + 1}.webp`;
        if (method !== "DELETE") state.images.set(filename, Buffer.from(body.data_base64, "base64"));
        world[`${kind}_media_id`] = method === "DELETE" ? null : `/media/worlds/${FEED_WORLD}/${filename}`;
        world.row_version++;
        return route.fulfill({ json: context() });
      }
      Object.assign(world, body, { row_version: world.row_version + 1 }); return route.fulfill({ json: context() });
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}
