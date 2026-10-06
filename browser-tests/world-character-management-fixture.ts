import type { Page, Route } from "@playwright/test";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installSocialChatFixture } from "./world-social-chat-fixture";

export const WORLD_AGENT = "synthetic-responder";
export const worldCharacterRoute = (id = WORLD_AGENT, world = FEED_WORLD) => `/worlds/${world}/characters/${id}`;

export function syntheticWorldCharacter(id: string, worldId = FEED_WORLD, enabled = false) {
  const user = id === ownerId(worldId);
  return {
    profile: { schema_version: "world-character-profile-v1", world_id: worldId, world_character_id: id, character_id: `character-${id}`,
      display_name: user ? "Synthetic World User" : id === WORLD_AGENT ? "Synthetic Responder" : `Synthetic ${id}`, handle: user ? "world_user" : id.replaceAll("-", "_"),
      avatar_url: null as string | null, banner_url: null as string | null, intro: `Original intro ${worldId} ${id}`, role_key: null,
      control_mode: user ? "owner_controlled" : "autonomous", status: "active", profile_capability: "available" },
    revision: 1, autonomous_enabled: !user && enabled, status: { state: enabled ? "outside_hours" : "off", reason: enabled ? "outside_active_hours" : null },
    settings: user ? null : { active_hours_start: "09:00", active_hours_end: "02:00", timezone: "Asia/Seoul", activity_interval_minutes: 30, max_posts_per_day: 30, max_comments_per_day: 30 },
    next_activity_at: null as string | null, recent_activity: user ? null : { action_type: "post", occurred_at: "2026-10-05T01:00:00Z", post_id: "synthetic-root", title: `Result in ${worldId}` },
    capabilities: { can_activate: !user && !enabled, can_deactivate: !user && enabled, can_run_now: !user, can_edit_profile: true, can_edit_settings: !user, can_view_graph: true, reason: null },
  };
}

export async function installWorldCharacterManagementRoutes(page: Page) {
  const worlds = new Map([FEED_WORLD, OTHER_FEED_WORLD].map(world => [world, [syntheticWorldCharacter("off-agent", world), syntheticWorldCharacter(WORLD_AGENT, world, true), syntheticWorldCharacter(ownerId(world), world)]]));
  const settings = new Map<string, Record<string, unknown>>();
  const state = { worlds, settings, reads: [] as string[], writes: [] as { path: string; method: string; body: Record<string, unknown> }[],
    completed: [] as { path: string; method: string; status: number }[],
    readDelay: 0, writeDelay: 0, readBarrier: null as Promise<void> | null, writeBarrier: null as Promise<void> | null,
    failure: 0, settingsFailure: 0, forbidden: false, readonly: false, corrupt: false,
    authOwner: undefined as string | null | undefined, authMeFailures: 0 };
  const dashboard = (world: string) => {
    const items = worlds.get(world)!;
    const users = items.filter(item => item.profile.control_mode === "owner_controlled").length;
    const enabled = items.filter(item => item.autonomous_enabled).length;
    return { contract_version: "world-character-dashboard-v1", world_id: state.corrupt ? "wrong-world" : world,
      summary: { total: items.length, enabled, disabled: items.length - enabled - users, users }, items };
  };
  const management = (world: string, id: string) => {
    const item = structuredClone(worlds.get(world)!.find(item => item.profile.world_character_id === id)!);
    if (state.readonly) { item.settings = null; item.recent_activity = null; item.capabilities = { ...item.capabilities, can_activate: false, can_deactivate: false, can_run_now: false, can_edit_profile: false, can_edit_settings: false }; }
    return { contract_version: "world-character-management-v1", world_id: state.corrupt ? "wrong-world" : world,
      world_character_id: id, character_id: item.profile.character_id, can_manage: !state.readonly, item };
  };
  const settingsRead = (world: string, id: string) => {
    const item = worlds.get(world)!.find(item => item.profile.world_character_id === id)!;
    const key = `${world}:${id}`;
    if (!settings.has(key)) settings.set(key, { ...item.settings, personality: `Original personality ${world}`, speech_style: "Plain voice", worldview: "Synthetic world",
      character_background: "Synthetic background", topic_preferences: "Synthetic topics", safety_rules: "Synthetic safety", generation_model: null, image_model: null, image_style: null, appearance_prompt: null });
    const { display_name, handle, intro, avatar_url, banner_url } = item.profile;
    return { contract_version: "world-character-settings-v1", world_id: world, world_character_id: id, revision: item.revision,
      profile: { display_name, handle, intro, avatar_url, banner_url }, settings: settings.get(key), capabilities: item.capabilities,
      supported_generation_models: [ { value: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite", enabled: true, reason: null } ],
      supported_image_models: [ { value: "flux-2-flex", label: "Flux 2 Flex", enabled: true, reason: null },
        { value: "gpt-image-1.5", label: "GPT Image 1.5", enabled: false, reason: "image_profile_required" } ] };
  };
  const handler = async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    if (path === "/auth/me" && state.authOwner !== undefined) {
      if (state.authOwner === null || state.authMeFailures > 0) {
        state.authMeFailures = Math.max(0, state.authMeFailures - 1);
        return route.fulfill({ status: 401, json: { detail: "Invalid token" } });
      }
      return route.fulfill({ json: { id: state.authOwner, display_name: "Synthetic Session Owner", email: null,
        profile_setup_completed: true, ui_language: "ko", ui_preference_revision: 1, feed_content_filter: "all", is_admin: true } });
    }
    if (path === "/auth/local/session" && state.authOwner !== undefined) {
      if (state.authOwner === null) return route.fulfill({ status: 503, json: { detail: "fixture_local_session_unavailable" } });
      return route.fulfill({ json: { user: { id: state.authOwner, display_name: "Synthetic Session Owner", email: null,
        profile_setup_completed: true, ui_language: "ko", ui_preference_revision: 1, feed_content_filter: "all", is_admin: true }, profile_setup_required: false } });
    }
    const entry = path.match(/^\/worlds\/([^/]+)\/world-characters\/([^/]+)\/chat-entry$/);
    if (entry && worlds.has(entry[1])) {
      const target = worlds.get(entry[1])!.find(item => item.profile.world_character_id === entry[2]);
      const requester = worlds.get(entry[1])!.find(item => item.profile.control_mode === "owner_controlled")!;
      if (target) return route.fulfill({ json: { schema_version: "world-chat-entry-v1", world_id: entry[1], responding: target.profile, requester: requester.profile,
        requester_cardinality: "one", create_or_get_capability: target === requester ? "unavailable" : "available", disabled_reason: target === requester ? "self_target" : null } });
    }
    const match = path.match(/^\/worlds\/([^/]+)\/(?:character-dashboard|world-characters\/([^/]+)\/(management|settings|profile(?:\/media)?|activate|deactivate|run-now))$/);
    if (!match) return route.fallback();
    const [, world, id, operation] = match;
    const respond = async (json: unknown, status = 200) => {
      await route.fulfill({ status, json });
      state.completed.push({ path, method, status });
    };
    if (method === "GET") state.reads.push(path); else state.writes.push({ path, method, body: request.postDataJSON() });
    const readSnapshot = method === "GET" && worlds.has(world) && (!id || worlds.get(world)!.some(item => item.profile.world_character_id === id))
      ? structuredClone(!id ? dashboard(world) : operation === "management" ? management(world, id) : settingsRead(world, id)) : null;
    const delay = method === "GET" ? state.readDelay : state.writeDelay;
    const barrier = method === "GET" ? state.readBarrier : state.writeBarrier;
    const failure = state.failure;
    if (barrier) await barrier;
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
    if (state.forbidden || !worlds.has(world)) return respond({ detail: "world_access_forbidden" }, 403);
    if (id && !worlds.get(world)!.some(item => item.profile.world_character_id === id)) return respond({ detail: "world_character_not_found" }, 404);
    if (method === "GET") {
      if (operation === "settings" && (state.readonly || state.settingsFailure)) return respond({ detail: "settings_unavailable" }, state.settingsFailure || 403);
      return respond(readSnapshot);
    }
    if (state.readonly) return respond({ detail: "world_owner_required" }, 403);
    if (failure) return respond({ detail: "synthetic_failure" }, failure);
    const item = worlds.get(world)!.find(item => item.profile.world_character_id === id)!;
    const body = request.postDataJSON();
    if (body.expected_revision !== item.revision) return respond({ detail: "world_character_revision_conflict" }, 409);
    if (operation === "activate" || operation === "deactivate") {
      item.autonomous_enabled = operation === "activate"; item.revision += 1;
      item.capabilities.can_activate = !item.autonomous_enabled; item.capabilities.can_deactivate = item.autonomous_enabled;
      return respond(dashboard(world));
    }
    if (operation === "profile") { const { expected_revision: _revision, ...values } = body; Object.assign(item.profile, values); item.revision += 1; return respond(management(world, id)); }
    if (operation === "profile/media") { item.profile[body.media_type === "avatar" ? "avatar_url" : "banner_url"] = `/api/v1/media/assets/synthetic-upload/content`; item.revision += 1; return respond(management(world, id)); }
    if (operation === "settings") { settingsRead(world, id); settings.set(`${world}:${id}`, { ...settings.get(`${world}:${id}`), ...body.settings }); Object.assign(item.settings!, body.settings); item.revision += 1; return respond(settingsRead(world, id)); }
    return respond({ contract_version: "world-character-run-now-v1", world_id: world, world_character_id: id, character_id: item.profile.character_id, revision: item.revision,
      run: { run_id: "synthetic-run", status: "accepted", summary: null, agent_id: "synthetic-slot", session_key: "synthetic-session", character_id: item.profile.character_id, post_id: null, gateway_result: {} } });
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}

export async function installWorldCharacterManagementFixture(page: Page, isStatic: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const base = await installSocialChatFixture(page, isStatic, baseURL, language);
  const management = await installWorldCharacterManagementRoutes(page);
  return { base, management };
}
