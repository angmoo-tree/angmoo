import { apiRequest } from "@/lib/http/api-request";
export type ActivityPolicy = {
    active_hours_start: string;
    active_hours_end: string;
    activity_interval_minutes: number;
    max_posts_per_day: number;
    max_comments_per_day: number;
    allow_post: boolean;
    allow_reply: boolean;
    allow_like: boolean;
};
export type BasicActivitySettings = {
    contract_version: "world-activity-settings-v1";
    world_id: string;
    world_character_id: string;
    character_id: string;
    revision: number;
    timezone: string;
    autonomous_enabled: boolean;
    policy: ActivityPolicy;
    can_activate: boolean;
    can_deactivate: boolean;
    reason: string | null;
};
const path = (world: string, actor: string) => `/worlds/${encodeURIComponent(world)}/world-characters/${encodeURIComponent(actor)}`;
function decode(value: unknown, world: string, actor: string): BasicActivitySettings {
    if (!value || typeof value !== "object") throw new Error("activity_settings_contract_invalid");
    const row = value as Record<string, unknown>;
    const policy = row.policy && typeof row.policy === "object" ? row.policy as Record<string, unknown> : null;
    if (row.contract_version !== "world-activity-settings-v1" || row.world_id !== world || row.world_character_id !== actor
        || typeof row.character_id !== "string" || !row.character_id || !Number.isInteger(row.revision) || Number(row.revision) < 1
        || typeof row.timezone !== "string" || !row.timezone
        || !["autonomous_enabled", "can_activate", "can_deactivate"].every(key => typeof row[key] === "boolean")
        || !(row.reason === null || typeof row.reason === "string") || !policy
        || !["active_hours_start", "active_hours_end"].every(key => typeof policy[key] === "string")
        || !["activity_interval_minutes", "max_posts_per_day", "max_comments_per_day"].every(key => Number.isInteger(policy[key]))
        || !["allow_post", "allow_reply", "allow_like"].every(key => typeof policy[key] === "boolean")) {
        throw new Error("activity_settings_contract_invalid");
    }
    return value as BasicActivitySettings;
}
export async function readBasicActivitySettings(world: string, actor: string, signal?: AbortSignal) {
    return decode(await apiRequest<unknown>(`${path(world, actor)}/activity-settings`, { signal }), world, actor);
}
export async function saveBasicActivitySettings(world: string, actor: string, revision: number, changes: Partial<ActivityPolicy>, signal?: AbortSignal) {
    return decode(await apiRequest<unknown>(`${path(world, actor)}/activity-settings`, { method: "PATCH", body: { expected_revision: revision, ...changes }, signal }), world, actor);
}
export const toggleBasicActivity = (world: string, actor: string, revision: number, enabled: boolean, signal?: AbortSignal) => apiRequest(`${path(world, actor)}/${enabled ? "activate" : "deactivate"}`, { method: "POST", body: { expected_revision: revision }, signal });
