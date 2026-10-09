import { expect, type Page, type Route } from "@playwright/test";
import type { AgentCreationDraftRead } from "../frontend/src/features/characters/types/agents";
import { installUiFixture } from "./world-ui-improvements-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT } from "./world-character-management-fixture";

export async function installIntegrationFixture(page: Page, isStatic: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const unexpected: string[] = [];
  // Unmatched API requests never reach the original app or a real provider.
  const reject = (route: Route) => {
    unexpected.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
    return route.fulfill({ status: 404, json: { detail: "unexpected_fixture_request" } });
  };
  await page.route("**/api/backend/**", reject);
  await page.route("http://127.0.0.1:8080/api/v1/**", reject);
  const ui = await installUiFixture(page, isStatic, baseURL, language);
  const state = {
    ui, unexpected, draftWorld: false, policyFailure: 0, snsFailure: 0,
    runtimeFailure: 0, runtimeDelay: 0, runtimeKnown: true, completeFailure: false,
    completeCalls: 0, registrations: 0, reads: [] as string[], writes: [] as { path: string; body: Record<string, unknown> }[],
    mood: "curious", note: "Original state note\n실제 저장된 확인 문장입니다.", confirmedAt: "2026-10-09T08:01:00Z" as string | null,
    engine: "personalized_graph_v2" as string | null, engineVersion: 1,
    transition: "ready" as "ready" | "pending_settlement" | "needs_preparation" | "pending_conversion",
    draft: null as AgentCreationDraftRead | null,
  };
  ui.management.worlds.get(FEED_WORLD)!.find(item => item.profile.world_character_id === WORLD_AGENT)!.autonomous_enabled = false;
  const policy = (world: string, actor: string) => {
    const item = ui.management.worlds.get(world)!.find(row => row.profile.world_character_id === actor)!;
    const saved = ui.management.settings.get(`${world}:${actor}`) ?? {
      active_hours_start: "09:00", active_hours_end: "02:00", activity_interval_minutes: 30,
      max_posts_per_day: 30, max_comments_per_day: 30, allow_post: true, allow_reply: true, allow_like: true,
    };
    const hasKey = Boolean(ui.management.credentials.get(`${world}:${actor}:sns`)?.has_key);
    return { contract_version: "world-activity-settings-v1", world_id: world, world_character_id: actor,
      character_id: item.profile.character_id, revision: item.revision, timezone: "Asia/Seoul", autonomous_enabled: item.autonomous_enabled,
      policy: Object.fromEntries(["active_hours_start", "active_hours_end", "activity_interval_minutes", "max_posts_per_day", "max_comments_per_day", "allow_post", "allow_reply", "allow_like"].map(key => [key, saved[key]])),
      can_activate: !state.draftWorld && hasKey && !item.autonomous_enabled,
      can_deactivate: item.autonomous_enabled, reason: state.draftWorld ? "world_not_published" : hasKey ? null : "credential_required" };
  };
  const handler = async (route: Route) => {
    const request = route.request(), url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    const body: Record<string, unknown> = method === "GET" ? {} : request.postDataJSON() ?? {};
    const reply = (value: unknown, status = 200) => route.fulfill({ json: value, status });
    const basic = path.match(/^\/worlds\/([^/]+)\/world-characters\/([^/]+)\/activity-settings$/);
    if (basic) {
      state.reads.push(path);
      if (method === "PATCH") {
        state.writes.push({ path, body });
        if (state.policyFailure) return reply({ detail: "synthetic_policy_failure" }, state.policyFailure);
        const [, world, actor] = basic, item = ui.management.worlds.get(world)!.find(row => row.profile.world_character_id === actor)!;
        expect(body.expected_revision).toBe(item.revision);
        const { expected_revision: _revision, ...changes } = body;
        ui.management.settings.set(`${world}:${actor}`, { ...policy(world, actor).policy, ...changes });
        item.revision++;
      }
      return reply(policy(basic[1], basic[2]));
    }
    const studio = path.match(/^\/worlds\/([^/]+)\/characters$/);
    if (studio && url.searchParams.get("surface") === "studio") {
      state.reads.push(path);
      return reply({ schema_version: "studio-world-character-list-v1", world_id: studio[1], items: ui.management.worlds.get(studio[1])!.map(item => ({
        world_character_id: item.profile.world_character_id, character_id: item.profile.character_id,
        display_name: item.profile.display_name, confirmation_name: item.profile.display_name, avatar_url: null,
        intro: item.profile.intro, role_key: null, control_mode: item.profile.control_mode, status: item.profile.status,
        autonomous_enabled: item.autonomous_enabled, selected_active_world: false, version: item.revision, activity_setup_state: "not_started",
      })) });
    }
    if (path.endsWith("/credentials/sns") && method !== "GET" && state.snsFailure) {
      state.writes.push({ path, body });
      return reply({ detail: "synthetic_sns_failure" }, state.snsFailure);
    }
    const runtime = path.match(/^\/worlds\/([^/]+)\/world-characters\/([^/]+)\/activity-runtime$/);
    if (runtime) {
      state.reads.push(path);
      if (method === "PUT") {
        state.writes.push({ path, body });
        expect(body.scope).toBe("character"); expect(body.expected_version).toBe(state.engineVersion);
        state.engine = body.engine === null ? null : String(body.engine); state.engineVersion++;
      }
      const snapshot = { world_id: runtime[1], world_character_id: runtime[2], autonomous_enabled: false, control_mode: "autonomous",
        effective: { engine: state.engine ?? "personalized_graph_v2", source: state.engine ? "character" : "world", version: state.engineVersion },
        transition: { state: state.transition, reason: null },
        policies: { character: { engine: state.engine, version: state.engineVersion }, world: { engine: "personalized_graph_v2", version: 1 }, global: { engine: null, version: 0 } },
        current_state: { known: state.runtimeKnown, version: 2, mood: state.runtimeKnown ? state.mood : null, mood_intensity: state.runtimeKnown ? 63 : null,
          state_note: state.runtimeKnown ? state.note : null, changed_at: "2026-10-09T08:00:00Z", confirmed_at: state.runtimeKnown ? state.confirmedAt : null }, runs: [] };
      const failure = state.runtimeFailure, delay = state.runtimeDelay;
      if (delay) await new Promise(resolve => setTimeout(resolve, delay));
      return reply(failure ? { detail: "synthetic_runtime_unavailable" } : snapshot, failure || 200);
    }
    if (path.startsWith("/agents/drafts")) {
      if (method !== "GET") state.writes.push({ path, body });
      if (path === "/agents/drafts" && method === "POST") {
        state.draft = { id: "integration-draft", revision: 1, contract_version: 2, target_world_id: String(body.target_world_id ?? FEED_WORLD),
          source_kind: "direct", status: "editing", provider: "google", model: "gemini-3.1-flash-lite", thinking_level: "high", key_fingerprint: null,
          name: "", handle: null, one_liner: "", worldview: "", personality: "", speech_style: "", character_background: "", topic_preferences: "", safety_rules: "",
          image_style: "기본", appearance_prompt: "", avatar_temp_url: null, banner_temp_url: null,
          persona_enhance_available_at: null, media_generation_available_at: null, expires_at: "2026-10-11T00:00:00Z", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z" };
        return reply(state.draft);
      }
      if (!state.draft) return reply({ detail: "draft_not_found" }, 404);
      if (path.endsWith("/complete")) {
        expect(body.revision).toBe(state.draft.revision); state.completeCalls++;
        if (state.draft.status !== "completed") { state.registrations++; state.draft.status = "completed"; }
        if (state.completeFailure) { state.completeFailure = false; return reply({ detail: "synthetic_response_lost" }, 503); }
        return reply({ character: { id: `character-${WORLD_AGENT}`, name: state.draft.name, execution_mode: "llm" },
          registration_scope: { world_id: state.draft.target_world_id, world_character_id: WORLD_AGENT, character_id: `character-${WORLD_AGENT}` } });
      }
      if (method === "PATCH") {
        expect(body.revision).toBe(state.draft.revision);
        Object.assign(state.draft, body, { revision: state.draft.revision + 1 });
      }
      return reply(state.draft);
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}
