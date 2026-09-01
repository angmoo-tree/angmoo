import type {
  MessageGoogleGeminiModel,
  MessageMessageRead,
} from "./chat-contract";

export type WorldChatControlMode = "autonomous" | "owner_controlled";

export type WorldChatRoleRead = {
  world_character_id: string;
  character_id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
  banner_url: string | null;
  role_key: string | null;
  control_mode: WorldChatControlMode;
  profile_capability: "available";
};

export type WorldChatEntryRead = {
  schema_version: "world-chat-entry-v1";
  world_id: string;
  responding: WorldChatRoleRead;
  requester_cardinality: "zero" | "one" | "anomaly";
  requester: WorldChatRoleRead | null;
  create_or_get_capability: "available" | "unavailable";
  disabled_reason:
    | "requester_missing"
    | "requester_cardinality_anomaly"
    | "self_target"
    | "blocked"
    | "target_not_chat_capable"
    | null;
};

export type WorldChatThreadRead = {
  id: string;
  world_id: string;
  requester: WorldChatRoleRead;
  responding: WorldChatRoleRead;
  selected_model: string;
  last_message_at: string | null;
  created_at: string;
  latest_message: MessageMessageRead | null;
  messages: MessageMessageRead[];
};

export type WorldChatThreadListRead = {
  items: WorldChatThreadRead[];
  ambiguous_legacy_count: number;
  max_threads: number;
};

export type WorldChatThreadCreate = {
  responding_world_character_id: string;
  requester_world_character_id?: string | null;
  selected_model?: MessageGoogleGeminiModel | null;
};

export type WorldChatThreadCreateRead = {
  outcome: "created" | "reused" | "resolution_required";
  thread: WorldChatThreadRead | null;
  resolution_code:
    | "requester_missing"
    | "requester_cardinality_anomaly"
    | null;
};

export function resolvedLegacyWorldChatRouteParts(thread: {
  id: string;
  requester_world_character_id: string | null;
  responding_world_character_id: string | null;
  world_id: string | null;
  world_scope_status: "resolved" | "ambiguous" | "quarantined";
}): { threadId: string; worldId: string } | null {
  if (
    thread.world_scope_status !== "resolved" ||
    !thread.world_id ||
    !thread.requester_world_character_id ||
    !thread.responding_world_character_id
  ) {
    return null;
  }
  return { threadId: thread.id, worldId: thread.world_id };
}
