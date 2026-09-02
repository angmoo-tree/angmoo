import type {
  MessageGoogleGeminiModel,
  MessageMessageRead,
} from "./chat-contract";

export type WorldChatControlMode = "autonomous" | "owner_controlled";
export type WorldChatModelBindingMode = "default" | "thread_override";

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
  selected_model: MessageGoogleGeminiModel;
  default_model: MessageGoogleGeminiModel;
  model_binding_mode: WorldChatModelBindingMode;
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

export type WorldChatThreadModelUpdate =
  | { mode: "default" }
  | {
      mode: "thread_override";
      selected_model: MessageGoogleGeminiModel;
    };

export type WorldChatGenerationState =
  | "accepted"
  | "lease_acquired"
  | "preflighted"
  | "routing"
  | "resolving"
  | "current_context_ready"
  | "canonical_planning"
  | "graph_planning"
  | "both_coordinating"
  | "clarification_prepared"
  | "optional_retrieving"
  | "evidence_frozen"
  | "response_generating"
  | "response_streaming"
  | "committing"
  | "committed"
  | "rejected"
  | "cancelled"
  | "timed_out"
  | "failed"
  | "orphaned";

export type WorldChatGenerationRequestRead = {
  protocol_version: "chat-generation-stream.v1";
  request_id: string;
  request_scope_hash: string;
  generation_id: string;
  attempt_number: number;
  response_slot_id: string;
  state: WorldChatGenerationState;
  route: "CURRENT_CONTEXT" | "CANONICAL" | "GRAPH" | "BOTH" | "CLARIFICATION" | null;
  retryable: boolean;
  failure_class: string | null;
  last_accepted_sequence: number;
  user_message: MessageMessageRead;
  assistant_message: MessageMessageRead | null;
  response_metadata: Record<string, unknown>;
};

export type WorldChatMessageAcceptRead = {
  outcome: "accepted" | "replayed";
  user_message: MessageMessageRead;
  response_request: WorldChatGenerationRequestRead;
};

export type WorldChatLatestRequestRead = {
  response_request: WorldChatGenerationRequestRead | null;
};

export type WorldChatGenerationEvent = {
  protocol_version: "chat-generation-stream.v1";
  request_id: string;
  request_scope_hash: string;
  generation_id: string;
  attempt_number: number;
  sequence: number;
  type: "accepted" | "delta" | "completed" | "failed" | "cancelled";
  payload:
    | Record<string, never>
    | { text: string }
    | { failure_class: string; retryable: boolean }
    | { reason: string };
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
