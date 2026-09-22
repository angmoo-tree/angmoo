import { apiRequest } from "@/lib/http/api-request";

export type ActivityEngine = "current" | "personalized_graph_v2";
export type EngineScope = "character" | "world" | "global";
export type ActivityRuntimeStatus = {
  world_id: string;
  world_character_id: string;
  autonomous_enabled: boolean;
  control_mode: string;
  effective: { engine: ActivityEngine; source: string; version: number };
  policies: Record<EngineScope, { engine: ActivityEngine | null; version: number }>;
  current_state: {
    known: boolean; version: number; mood: string | null; mood_intensity: number | null;
    state_note: string | null; changed_at: string | null; confirmed_at: string | null;
  };
  runs: Array<{ activity_id: string; engine: string; status: string; stage: string;
    paths: Record<string, { status: string; state_status: string | null; public_action_count: number; selected_count: number; recall_count: number; reason: string | null }>;
    started_at: string; finished_at: string | null; public_action_count: number | null; reason: string | null }>;
};

function path(worldId: string, actorId: string) {
  return `/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(actorId)}/activity-runtime`;
}

export function getActivityRuntime(worldId: string, actorId: string, signal?: AbortSignal) {
  return apiRequest<ActivityRuntimeStatus>(path(worldId, actorId), { signal });
}

export function setActivityEngine(worldId: string, actorId: string, scope: EngineScope, engine: ActivityEngine | null, expectedVersion: number) {
  return apiRequest<ActivityRuntimeStatus>(path(worldId, actorId), {
    method: "PUT", body: { scope, engine, expected_version: expectedVersion },
  });
}
