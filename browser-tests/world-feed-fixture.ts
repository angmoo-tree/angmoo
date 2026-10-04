import type { Page, Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { uiDManualFeed, uiDManualPost, uiDOwnerActor, uiDWorld } from "./continuity-next-fixture";
import { continuityAgentDetail } from "./continuity-fixture";
import { VISUAL_ENVIRONMENT } from "./fixtures/visual-environment.mjs";

export const FEED_WORLD = "world-feed-alpha";
export const OTHER_FEED_WORLD = "world-feed-beta";
export const OWNER_NAME = "Synthetic World User";
export const OWNER_HANDLE = "world_user";
export const feedRoute = (world = FEED_WORLD) => `/worlds/${world}/feed`;
export const ownerId = (world = FEED_WORLD) => `owner-${world}`;
export const profileRoute = (world = FEED_WORLD) => `/worlds/${world}/characters/${ownerId(world)}`;

type Write = { path: string; method: string; body: Record<string, unknown> | null; key: string | null };
export type FeedFixture = {
  language: "ko" | "en";
  feedFailures: number;
  postFailures: number;
  uploadFailures: number;
  postDelay: number;
  uploadDelay: number;
  missingOwner: boolean;
  ownerFailures: number;
  ownerDelays: Record<string, number>;
  worldForbidden: boolean;
  avatar: boolean;
  displayName: string;
  globalName: string;
  handle: string | null;
  writes: Write[];
  environmentWrites: Write[];
  reads: string[];
  unexpected: string[];
  providerCalls: string[];
  discarded: string[];
  posts: ReturnType<typeof uiDManualPost>[];
  ownerReads: Record<string, number>;
  ownerResponses: string[];
};

export async function installWorldFeedFixture(page: Page, staticShell: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const state: FeedFixture = {
    language, feedFailures: 0, postFailures: 0, uploadFailures: 0,
    postDelay: 0, uploadDelay: 0, missingOwner: false, ownerFailures: 0, ownerDelays: {}, worldForbidden: false, avatar: true,
    globalName: "Synthetic Autonomous Agent", handle: OWNER_HANDLE,
    displayName: OWNER_NAME, writes: [], environmentWrites: [], reads: [], unexpected: [], providerCalls: [], discarded: [],
    posts: [], ownerReads: {}, ownerResponses: [],
  };
  const baseOrigin = new URL(baseURL).origin;
  await page.route("**/*", route => new URL(route.request().url()).origin === baseOrigin
    ? route.fallback() : route.abort("blockedbyclient"));
  if (staticShell) await page.addInitScript(() => Object.assign(window, {
    __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: "world-feed-synthetic-token-0000000000" },
  }));
  const assets = new Map<string, { bytes: Buffer; mime: string }>();
  const saved = new Map<string, ReturnType<typeof uiDManualPost>>();
  let assetNumber = 0;
  const owner = (world: string) => ({
    ...uiDOwnerActor(world), world_character_id: ownerId(world), character_id: `character-${ownerId(world)}`,
    profile: { ...uiDOwnerActor(world).profile, display_name: world === FEED_WORLD ? state.displayName : "Other World User",
      handle: world === FEED_WORLD ? state.handle : "other_user", avatar_url: state.avatar ? "/api/v1/media/assets/owner-avatar/content" : null },
  });
  const readFeed = (world: string) => ({ ...uiDManualFeed(state.posts.map(post => ({ ...post, world_id: world })), world), owner_world_character_id: ownerId(world) });
  const reply = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });
  const handler = async (route: Route) => {
    const request = route.request(), url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    if (["GET", "HEAD"].includes(method)) state.reads.push(path);
    else {
      const write = { path, method, body: request.postData() ? request.postDataJSON() : null, key: request.headers()["idempotency-key"] ?? null };
      // Auth bootstrap reports the UI environment even when the user only reads
      // a feed. Audit it separately from Social/Media writes, without hiding it.
      (path === "/auth/local/environment" ? state.environmentWrites : state.writes).push(write);
    }
    if (/generate|completion|preflight/.test(path)) state.providerCalls.push(path);
    if (path === "/auth/me") return reply(route, { id: "local-owner", display_name: "Local Owner", email: null, profile_setup_completed: true,
      ui_language: state.language, ui_preference_revision: 1, feed_content_filter: "all", is_admin: true });
    if (path === "/auth/local/environment") return reply(route, { ...VISUAL_ENVIRONMENT, preferred_language: state.language, memory_search_locale: state.language });
    if (path === "/runtime/status") return reply(route, { schema_version: "local-runtime-status-v1", installation_state: "ready" });
    if (path === "/maintenance/agent-activity") return reply(route, { enabled: false, blocks_feed_cues: false, notice_enabled: false });
    if (path === "/agents") {
      const agent = continuityAgentDetail("global-character");
      return reply(route, [{ ...agent, settings: { ...agent.settings, auto_enabled: true },
        character: { ...agent.character, name: state.globalName, handle: OWNER_HANDLE, avatar_url: owner(FEED_WORLD).profile.avatar_url } }]);
    }
    if (path.endsWith("/feed-cue")) return reply(route, null);
    if (path === "/feed" || path.startsWith("/feed/following")) return reply(route, { items: state.posts.map(post => ({ ...post,
      author_character_id: "fixture-autonomous-author", mentioned_characters: [], media: [], quoted_post: null, reposted_post: null })), next_cursor: null });
    if (path === "/worlds/default-space/ensure") return reply(route, { id: FEED_WORLD, name: "SNS", timezone: "Asia/Seoul" });
    if (path === "/worlds/mine") return reply(route, { schema_version: "local-world-surface-v1", surface: url.searchParams.get("surface"),
      items: [uiDWorld(FEED_WORLD), uiDWorld(OTHER_FEED_WORLD)], next_cursor: null });
    const worldRead = path.match(/^\/worlds\/mine\/([^/]+)$/);
    if (worldRead) return state.worldForbidden ? reply(route, { detail: "world_not_found" }, 404)
      : reply(route, { schema_version: "local-world-app-v1", surface: "world_app", world: uiDWorld(worldRead[1]) });
    const ownerRead = path.match(/^\/worlds\/([^/]+)\/owner-character$/);
    if (ownerRead) {
      state.ownerReads[ownerRead[1]] = (state.ownerReads[ownerRead[1]] ?? 0) + 1;
      const snapshot = owner(ownerRead[1]);
      if (state.ownerDelays[ownerRead[1]]) await new Promise(resolve => setTimeout(resolve, state.ownerDelays[ownerRead[1]]));
      if (state.ownerFailures-- > 0) return reply(route, { detail: "owner_read_unavailable" }, 503);
      if (state.missingOwner) return reply(route, { detail: "owner_character_not_found" }, 404);
      await reply(route, snapshot); state.ownerResponses.push(ownerRead[1]); return;
    }
    const ensure = path.match(/^\/worlds\/([^/]+)\/my-profile\/ensure$/);
    if (ensure) { state.missingOwner = false; return reply(route, owner(ensure[1])); }
    const patchProfile = path.match(/^\/worlds\/([^/]+)\/my-profile$/);
    if (patchProfile && method === "PATCH") {
      const data = request.postDataJSON(); state.displayName = data.display_name; state.handle = data.handle;
      return reply(route, owner(patchProfile[1]));
    }
    const chatEntry = path.match(/^\/worlds\/([^/]+)\/world-characters\/([^/]+)\/chat-entry$/);
    if (chatEntry) {
      const actor = owner(chatEntry[1]), role = { ...actor.profile, world_character_id: actor.world_character_id,
        character_id: actor.character_id, control_mode: "owner_controlled", profile_capability: "available" };
      return reply(route, { schema_version: "world-chat-entry-v1", world_id: chatEntry[1], responding: role,
        requester: role, requester_cardinality: "one", create_or_get_capability: "unavailable", disabled_reason: "self_target" });
    }
    const socialProfile = path.match(/^\/worlds\/([^/]+)\/world-characters\/([^/]+)\/social-profile$/);
    if (socialProfile) return reply(route, { schema_version: "world-character-social-profile-v1", world_id: socialProfile[1],
      world_character_id: socialProfile[2], character_id: `character-${socialProfile[2]}`, tab: url.searchParams.get("tab"),
      counts: { post_count: 0, reply_count: 0, liked_post_count: 0, received_like_count: 0 }, items: [], next_cursor: null });
    const profile = path.match(/^\/worlds\/([^/]+)\/world-characters\/([^/]+)$/);
    if (profile) return reply(route, { schema_version: "world-character-profile-v1", world_id: profile[1], world_character_id: profile[2],
      character_id: `character-${profile[2]}`, display_name: owner(profile[1]).profile.display_name, handle: owner(profile[1]).profile.handle,
      avatar_url: owner(profile[1]).profile.avatar_url, banner_url: null, intro: "Synthetic profile", role_key: null,
      control_mode: "owner_controlled", status: "active", profile_capability: "available" });
    const feed = path.match(/^\/worlds\/([^/]+)\/manual-social\/feed$/);
    if (feed) {
      if (state.feedFailures-- > 0) return reply(route, { detail: "sqlite_busy_retry_exhausted" }, 503);
      return reply(route, readFeed(feed[1]));
    }
    const write = path.match(/^\/worlds\/([^/]+)\/manual-social\/posts$/);
    if (write && method === "POST") {
      if (state.postDelay) await new Promise(resolve => setTimeout(resolve, state.postDelay));
      if (state.postFailures-- > 0) return reply(route, { detail: "sqlite_busy_retry_exhausted" }, 503);
      const data = request.postDataJSON(), key = request.headers()["idempotency-key"];
      const previous = saved.get(key);
      const post = previous ?? { ...uiDManualPost({ id: `created-${saved.size + 1}`, title: data.title, body: data.body, authorName: state.displayName, worldId: write[1] }),
        author_world_character_id: ownerId(write[1]), author_handle: OWNER_HANDLE,
        media: data.attachment_asset_id ? [{ id: 1, asset_id: data.attachment_asset_id, media_type: "image", source_kind: "upload",
          url: `/api/v1/media/assets/${data.attachment_asset_id}/content`, alt_text: "Uploaded photo", width: 18, height: 24 }] : [] };
      if (!previous) { saved.set(key, post); state.posts.unshift(post); }
      return reply(route, { schema_version: "owner-manual-social-v1", operation: "post", post, replayed: Boolean(previous),
        delivery: { provider_call_count: 0, inbox_candidate_id: null, inbox_status: "not_applicable", public_reaction_required: false } }, 201);
    }
    const thread = path.match(/^\/worlds\/([^/]+)\/manual-social\/posts\/([^/]+)$/);
    if (thread) return reply(route, { ...readFeed(thread[1]), root_post_id: thread[2], target_post_id: thread[2], next_offset: null,
      items: [{ ...uiDManualPost({ id: thread[2], title: "Synthetic thread title", body: "Synthetic thread body", worldId: thread[1] }), reply_count: 0 }] });
    if (path === "/media/assets" && method === "POST") {
      if (state.uploadDelay) await new Promise(resolve => setTimeout(resolve, state.uploadDelay));
      if (state.uploadFailures-- > 0) return reply(route, { detail: "image_invalid" }, 422);
      const data = request.postDataJSON(), id = `draft-${++assetNumber}`;
      assets.set(id, { bytes: Buffer.from(data.data_base64, "base64"), mime: data.content_type });
      return reply(route, { id, url: `/api/v1/media/assets/${id}/content`, revision: 1, width: 18, height: 24, state: "draft", byte_size: assets.get(id)!.bytes.length }, 201);
    }
    const content = path.match(/^\/media\/assets\/([^/]+)\/content$/);
    if (content) {
      const asset = assets.get(content[1]) ?? { bytes: readFileSync("../backend/tests/image_integration/fixtures/pixels.png"), mime: "image/png" };
      return route.fulfill({ contentType: asset.mime, body: asset.bytes });
    }
    const discard = path.match(/^\/media\/assets\/([^/]+)$/);
    if (discard && method === "DELETE") { state.discarded.push(discard[1]); return route.fulfill({ status: 204 }); }
    if (path.endsWith("/image-generation")) return reply(route, null);
    state.unexpected.push(`${method} ${path}`);
    return reply(route, { detail: "world_feed_fixture_unexpected_request" }, 404);
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}
