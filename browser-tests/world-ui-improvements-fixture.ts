import { expect, type Page, type Route } from "@playwright/test";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD, ownerId } from "./world-feed-fixture";
import { memoryBatchFixture } from "./memory-batch-fixture";
import type { DailyActivityPlanRead } from "../frontend/src/features/characters/api/world-activity-runtime";
import { continuityAgentDetail } from "./continuity-fixture";

/** Dev-only equivalent of the existing static export document fallback.
 * The request URL and query remain unchanged; the real StaticProductRouter runs.
 */
export async function staticDocumentFallback(page: Page, baseURL: string) {
  await page.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.isNavigationRequest() && request.resourceType() === "document" && url.origin === new URL(baseURL).origin && url.pathname !== "/") {
      const response = await route.fetch({ url: `${baseURL}/` });
      return route.fulfill({ response });
    }
    return route.fallback();
  });
}

export async function installUiFixture(page: Page, isStatic: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const base = await installWorldCharacterManagementFixture(page, isStatic, baseURL, language);
  if (isStatic) await staticDocumentFallback(page, baseURL);
  const plan: DailyActivityPlanRead = {
    id: "plan-1", world_id: FEED_WORLD, world_character_id: WORLD_AGENT, local_date: "2026-10-09",
    timezone_name: "Asia/Seoul", timezone_contract_version: "world.v1", repertoire_id: null,
    world_definition_hash: "synthetic", character_definition_hash: "synthetic", repertoire_contract_version: "synthetic",
    selection_contract_version: "synthetic", selection_seed_hash: "synthetic", status: "active", revision_count: 0, version: 2,
    autonomous_enabled: true, activity_runtime_mode: "routine_resident_v1", current_daypart: "afternoon", reused: true,
    items: ["dawn", "morning", "afternoon", "evening"].map((part, index) => ({
      id: `item-${part}`, daypart: part as "dawn" | "morning" | "afternoon" | "evening", selected_candidate_id: null,
      candidate_signature: null, candidate_ordinal: null, origin_type: "daily_generation", supersedes_plan_item_id: null,
      is_user_pinned: false, activity_kind: "ordinary", title: `Original ${part} title ${"long text ".repeat(10)}`,
      activity_seed: `Original ${part} seed\n${"Untranslated full original. ".repeat(15)}`, social_mode: "none", place_key: null,
      joint_activity_id: null, scheduled_start_at: "2026-10-09T00:00:00Z", scheduled_end_at: "2026-10-09T09:00:00Z",
      status: index === 0 ? "completed" : index === 1 ? "active" : index === 2 ? "planned" : "skipped",
      revision_count: 0, terminal_reason_code: null, episode: null,
    })),
  };
  const state = { ...base, plan: plan as DailyActivityPlanRead | null, planVersion: 2, planDate: "2026-10-09",
    planState: "ready", requestState: null as string | null, topics: Array.from({ length: 10 }, (_, i) => `Original topic ${i + 1}`),
    topicState: "ready", failure: 0, delay: 0, reads: [] as string[], writes: [] as string[],
    graphFailure: 0, graphSource: "ladybug", graphStatus: "healthy", graphEmpty: false, graphDelay: 0,
    selectedKeys: new Map<string, { provider: string; has_key: boolean; fingerprint: string | null; key_revision: number }>([
      ["novelai", { provider: "novelai", has_key: true, fingerprint: "novel-fingerprint", key_revision: 1 }],
      ["openrouter", { provider: "openrouter", has_key: true, fingerprint: "router-fingerprint", key_revision: 1 }],
      ["comfyui", { provider: "comfyui", has_key: true, fingerprint: "partner-fingerprint", key_revision: 1 }],
    ]),
  };
  const handler = async (route: Route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path === "/media/catalog") return route.fulfill({ json: { quota_timezone: "Asia/Seoul", max_images: 1, upload_limit_bytes: 10485760, models: [
      { provider: "novelai", id: "nai-diffusion-4-5-full", reference_supported: true, parameters: {}, prompt_validation: { generation_available: true } },
      { provider: "openrouter", id: "openai/gpt-image-2.5-flare", reference_supported: false, parameters: {} },
      { provider: "openrouter", id: "google/gemini-3.1-flash-image", reference_supported: true, parameters: {} },
    ] } });
    const daily = path.match(/\/characters\/character-([^/]+)\/worlds\/([^/]+)\/(activity-plan|daily-preparation)$/);
    if (daily || path.endsWith("/recommendation-topics")) {
      if (request.method() !== "GET") { state.writes.push(path); return route.fulfill({ status: 422, json: { detail: "fixture_no_generation" } }); }
      state.reads.push(url.pathname + url.search);
      const body = daily ? daily[3] === "activity-plan" ? structuredClone(state.plan) : {
        world_character_id: daily[1], local_date: state.planDate, plan_state: state.planState, topic_state: state.topicState,
        request_id: null, attempt_count: 0, reason_code: null, plan_id: state.plan?.id ?? null, plan_version: state.planVersion,
        request_state: state.requestState, request_reason_code: null, next_retry_at: null,
      } : { world_id: FEED_WORLD, world_character_id: url.searchParams.get("world_character_id"), state: state.topicState,
        topics: state.topics.map((name, index) => ({ id: `topic-${index}`, name, scope: "world" })), key_world_character_id: WORLD_AGENT,
        model: "gemini-3.1-flash-lite", thinking_level: "high", last_code: null, approval_required: false, recent_deliveries: [], recent_feed: [] };
      const failure = state.failure;
      if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
      return route.fulfill({ status: failure || 200, json: failure ? { detail: "synthetic_unavailable" } : body });
    }
    const key = path.match(/\/image-provider-key\/(\w+)$/);
    if (key) {
      state.reads.push(path);
      const body = structuredClone(state.selectedKeys.get(key[1]) ?? { provider: key[1], has_key: false, fingerprint: null, key_revision: 0 });
      if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
      return route.fulfill({ status: state.failure || 200, json: state.failure ? { detail: "synthetic_unavailable" } : body });
    }
    if (path.endsWith("/credentials/image")) {
      const key = `${FEED_WORLD}:${WORLD_AGENT}:image`;
      let value = state.management.credentials.get(key) ?? { provider: "novelai", model: "nai-diffusion-4-5-full", thinking_level: null,
        has_key: true, has_partner_key: false, fingerprint: "novel-fingerprint", revision: 1, key_revision: 1, configuration_revision: 1 };
      if (request.method() !== "GET") {
        const body = request.postDataJSON(); state.writes.push(path);
        expect(body.expected_revision).toBe(value.revision);
        const provider = String(body.provider ?? value.provider), providerKey = state.selectedKeys.get(provider)!;
        expect(body.expected_key_revision).toBe(providerKey.key_revision);
        if (request.method() === "DELETE") state.selectedKeys.set(provider, { ...providerKey, has_key: false, fingerprint: null, key_revision: providerKey.key_revision + 1 });
        else {
          expect(body.provider === "comfyui" ? body.api_key : undefined).toBeUndefined();
          value = { ...value, provider, model: body.model, has_key: provider !== "comfyui" && providerKey.has_key,
            has_partner_key: provider === "comfyui" && providerKey.has_key, fingerprint: providerKey.fingerprint, revision: Number(value.revision) + 1 };
        }
      }
      state.management.credentials.set(key, value);
      return route.fulfill({ json: value });
    }
    const graph = path.match(/^\/characters\/(.+)\/worlds\/(.+)\/relationship-graph$/);
    if (graph) {
      state.reads.push(path + url.search); expect(url.searchParams.get("limit")).toBe("20"); expect(url.searchParams.get("provider")).toBe("ladybug");
      const delay = state.graphDelay;
      if (delay) await new Promise(resolve => setTimeout(resolve, delay));
      if (state.graphFailure) return route.fulfill({ status: state.graphFailure, json: { detail: "synthetic_graph_access" } });
      const center = graph[1].replace(/^character-/, ""), target = center === WORLD_AGENT ? ownerId() : WORLD_AGENT;
      return route.fulfill({ json: { world_id: graph[2], center_world_character_id: center,
        nodes: [{ world_character_id: center, character_id: graph[1], display_name: `Center ${center}`, is_center: true, avatar_url: null },
          ...(!state.graphEmpty ? [{ world_character_id: target, character_id: `character-${target}`, display_name: `Target ${target}`, is_center: false, avatar_url: null }] : [])],
        edges: state.graphEmpty ? [] : [{ relationship_state_id: "edge", actor_world_character_id: center, target_world_character_id: target,
          familiarity: 2, affinity: 1, trust: 3, tension: 0, interaction_count: 4, relationship_version: 2,
          relationship_label: "Original directed relationship", perception: "Original perception", view_updated_at: null, reviewed_at: null, last_event_id: null, last_event_at: null }],
        evidence: state.graphEmpty ? [] : [{ event_id: "synthetic-evidence", event_type: "reply_created",
          occurred_at: "2026-10-09T08:00:00Z", actor_world_character_id: center, target_world_character_id: target,
          root_post_id: "synthetic-evidence-post", source_post_id: "synthetic-evidence-reply" }],
        meta: { template: "neighborhood", source: state.graphSource, graph_status: state.graphStatus, truncated: false,
          projection_lag_seconds: 0, revalidated_node_count: 2, revalidated_edge_count: state.graphEmpty ? 0 : 1, fallback_reason: null } } });
    }
    if (path.endsWith("/relationship-review")) return route.fulfill({ json: { mode: "disabled", configuration: { status: "disabled" }, excluded_counts: {}, states: [], jobs: [] } });
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}

export async function installMemoryUi(page: Page, worldId = FEED_WORLD, subjectId = WORLD_AGENT) {
  const scope = { world_id: worldId, subject_world_character_id: subjectId }, capabilities = { read: "available", mutate: "available" };
  const state = { enabled: true, semantic: true, hasKey: true, failure: 0, revision: 1, preparation: "needs_preparation", runtime: "ready",
    reads: [] as string[], writes: [] as string[], delay: 0 };
  const batch = memoryBatchFixture(worldId, subjectId, () => state.enabled);
  const handler = async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    if (path.endsWith(`/worlds/${worldId}/world-characters`)) return route.fulfill({ json: {
      schema_version: "world-character-profile-list-v1", world_id: worldId, items: [syntheticWorldCharacter(subjectId, worldId).profile],
    } });
    if (!path.includes(`/worlds/${worldId}/world-characters/${subjectId}/`)) return route.fallback();
    if (method === "GET") state.reads.push(path); else state.writes.push(path);
    const reply = (json: unknown, status = 200) => route.fulfill({ json, status });
    if (path.endsWith("/credentials/embedding")) {
      if (method !== "GET") { state.hasKey = method !== "DELETE"; state.revision++; }
      return reply({ provider: "google", model: "gemini-embedding-2", thinking_level: null, has_key: state.hasKey,
        fingerprint: state.hasKey ? "synthetic-fingerprint" : null, revision: state.revision, configuration_revision: 0 });
    }
    if (path.endsWith("/memory/embedding-settings")) {
      if (method === "PUT") { state.semantic = request.postDataJSON().enabled; state.revision++; }
      if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
      return reply(state.failure ? { detail: "synthetic_read_error" } : { scope, enabled: state.semantic, provider: "google", model: "gemini-embedding-2",
        credential_id: null, profile: "synthetic-profile", version: state.revision, ready: state.hasKey && state.semantic, reason_code: null,
        runtime_status: state.runtime, available_credentials: [], preparation_state: state.preparation, preparation_revision: 0 }, state.failure || 200);
    }
    if (path.endsWith("/memory/embedding-preparation")) { state.preparation = "ready"; return reply({ scope, state: "pending" }, 202); }
    if (path.endsWith("/memory/settings")) return reply({ schema_version: "memory-setting-read.v1", scope, configured: true, enabled: state.enabled,
      retention_days: 180, provider_mode: "none", version: 1, capabilities });
    if (path.endsWith("/memories")) return reply({ schema_version: "memory-item-list.v1", scope, memory_enabled: state.enabled, items: [], next_cursor: null, capabilities });
    if (path.endsWith("/memory/unsaved-experiences")) return reply({ scope, items: [], next_cursor: null, blocked_count: 0, scope_busy: false, can_recheck: false });
    if (path.endsWith("/memory/processing-settings")) return reply({ scope, version: 1, memory_enabled: state.enabled, daily_enabled: true, local_time: "19:30",
      timezone: "Asia/Seoul", shutdown_apply_enabled: true, next_due_at: null, last_applied_at: null,
      pending_count: 0, blocked_count: 0, applied_count: 0, status: "idle", result: null });
    if (await batch(route)) return;
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}

export async function installLegacyImageUi(page: Page) {
  const keys = new Map(["novelai", "comfyui", "openrouter"].map(provider => [provider, { provider, has_key: true, fingerprint: `synthetic-${provider}`, key_revision: 1 }]));
  const profile = { active: true, reference_initialized: true, reference_enabled: false, options: { mode: "opus_free" }, connection: null };
  let saved = { character_id: WORLD_AGENT, revision: 1, installation_revision: 1, provider: "novelai", model: "nai-diffusion-4-5-full",
    auto_enabled: false, daily_limit: 20, installation_daily_limit: 20, appearance: "", style: "", negative: "", reference_asset_id: null,
    has_api_key: true, has_partner_api_key: true, profiles: {} as Record<string, unknown>, active_profile: profile as Record<string, unknown> };
  const state = { writes: [] as Record<string, unknown>[], reads: [] as string[], delay: 0, failure: 0, keys };
  const handler = async (route: Route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path === `/agents/${WORLD_AGENT}`) return route.fulfill({ json: continuityAgentDetail(WORLD_AGENT) });
    if (path.endsWith("/lore-sources")) return route.fulfill({ json: { items: [] } });
    const selected = path.match(/\/generation-provider-key\/(\w+)$/);
    if (selected) {
      state.reads.push(path); const snapshot = structuredClone(keys.get(selected[1]));
      if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
      return route.fulfill({ status: state.failure || 200, json: state.failure ? { detail: "synthetic_key_unavailable" } : snapshot });
    }
    if (path.endsWith("/generation-settings")) {
      if (route.request().method() !== "GET") {
        const body = route.request().postDataJSON(); state.writes.push(body);
        expect(body.expected_revision).toBe(saved.revision);
        if (body.provider === "comfyui") expect(body.api_key).toBeUndefined();
        if (body.clear_api_key) keys.set(body.provider, { ...keys.get(body.provider)!, has_key: false, fingerprint: "", key_revision: 2 });
        const active = { ...profile, options: body.options };
        saved = { ...saved, ...body, revision: saved.revision + 1, installation_revision: saved.installation_revision + 1,
          profiles: { ...saved.profiles, [`${body.provider}:${body.model}:${body.options.mode ?? ""}`]: active }, active_profile: active };
      }
      return route.fulfill({ json: saved });
    }
    if (path === "/media/catalog") return route.fulfill({ json: { quota_timezone: "Asia/Seoul", upload_limit_bytes: 10485760, models: [
      { provider: "novelai", id: "nai-diffusion-4-5-full", reference_supported: true, parameters: {} },
      { provider: "openrouter", id: "openai/gpt-image-2.5-flare", reference_supported: false, parameters: {} },
      { provider: "openrouter", id: "google/gemini-3.1-flash-image", reference_supported: true, parameters: {} },
    ] } });
    if (path === "/media/comfy-workflows/analyze") {
      const body = route.request().postDataJSON();
      return route.fulfill({ json: { prompt: JSON.parse(body.source_json), input_mode: body.input_mode, positions: [], notices: [], supported_tokens: {},
        used_roles: [], reference_required: false, prompt_applied: false, source_digest: "synthetic-fixed" } });
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}
