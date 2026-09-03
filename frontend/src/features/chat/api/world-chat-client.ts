import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";

import type {
  WorldChatGenerationEvent,
  WorldChatGenerationRequestRead,
  WorldChatLatestRequestRead,
  WorldChatMessageAcceptRead,
  WorldChatThreadCreate,
  WorldChatThreadCreateRead,
  WorldChatEntryRead,
  WorldChatThreadListRead,
  WorldChatThreadModelUpdate,
  WorldChatThreadRead,
} from "../model/world-chat-contract";
import { MESSAGE_GOOGLE_GEMINI_MODELS } from "../model/chat-contract";

type WorldChatRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

export class WorldChatApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "WorldChatApiError";
  }
}

export async function listWorldChatThreads(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldChatThreadListRead> {
  const payload = await requestWorldChatApi<WorldChatThreadListRead>(
    worldChatApiPath(worldId, "/threads"),
    { signal: options.signal },
  );
  if (
    !payload ||
    !Array.isArray(payload.items) ||
    typeof payload.ambiguous_legacy_count !== "number" ||
    typeof payload.max_threads !== "number" ||
    payload.items.some((thread) => !worldChatThreadMatchesScope(thread, worldId))
  ) {
    throw new WorldChatApiError(502, "world_chat_scope_mismatch");
  }
  return payload;
}

export async function getWorldChatEntry(
  worldId: string,
  respondingWorldCharacterId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldChatEntryRead> {
  const payload = await requestWorldChatApi<WorldChatEntryRead>(
    `/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(respondingWorldCharacterId)}/chat-entry`,
    { signal: options.signal },
  );
  if (
    payload?.schema_version !== "world-chat-entry-v1" ||
    payload.world_id !== worldId ||
    payload.responding?.world_character_id !== respondingWorldCharacterId ||
    payload.responding.profile_capability !== "available" ||
    (payload.requester && payload.requester.control_mode !== "owner_controlled") ||
    (payload.requester_cardinality === "one" && !payload.requester) ||
    (payload.requester_cardinality !== "one" && payload.requester !== null) ||
    (payload.create_or_get_capability === "available" &&
      (payload.requester_cardinality !== "one" || payload.disabled_reason !== null))
  ) {
    throw new WorldChatApiError(502, "world_chat_entry_scope_mismatch");
  }
  return payload;
}

export async function getWorldChatThread(
  worldId: string,
  threadId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldChatThreadRead> {
  const payload = await requestWorldChatApi<WorldChatThreadRead>(
    worldChatApiPath(worldId, `/threads/${encodeURIComponent(threadId)}`),
    { signal: options.signal },
  );
  if (
    !worldChatThreadMatchesScope(payload, worldId) ||
    payload.id !== threadId
  ) {
    throw new WorldChatApiError(502, "world_chat_scope_mismatch");
  }
  return payload;
}

export async function createOrGetWorldChatThread(
  worldId: string,
  data: WorldChatThreadCreate,
): Promise<WorldChatThreadCreateRead> {
  const payload = await requestWorldChatApi<WorldChatThreadCreateRead>(
    worldChatApiPath(worldId, "/threads"),
    { body: data, method: "POST" },
  );
  const validOutcome = ["created", "reused", "resolution_required"].includes(
    payload?.outcome,
  );
  const requiresThread = payload?.outcome === "created" || payload?.outcome === "reused";
  if (
    !validOutcome ||
    (requiresThread && !payload.thread) ||
    (payload.thread && !worldChatThreadMatchesScope(payload.thread, worldId))
  ) {
    throw new WorldChatApiError(502, "world_chat_scope_mismatch");
  }
  return payload;
}

export async function updateWorldChatThreadModel(
  worldId: string,
  threadId: string,
  data: WorldChatThreadModelUpdate,
): Promise<WorldChatThreadRead> {
  const payload = await requestWorldChatApi<WorldChatThreadRead>(
    worldChatApiPath(
      worldId,
      `/threads/${encodeURIComponent(threadId)}/model`,
    ),
    { body: data, method: "PATCH" },
  );
  if (
    !worldChatThreadMatchesScope(payload, worldId) ||
    payload.id !== threadId
  ) {
    throw new WorldChatApiError(502, "world_chat_scope_mismatch");
  }
  return payload;
}

export async function sendWorldChatMessage(
  worldId: string,
  threadId: string,
  data: { content: string; idempotency_key: string },
): Promise<WorldChatMessageAcceptRead> {
  const payload = await requestWorldChatApi<WorldChatMessageAcceptRead>(
    worldChatApiPath(
      worldId,
      `/threads/${encodeURIComponent(threadId)}/messages`,
    ),
    { body: data, method: "POST" },
  );
  if (!worldChatMessageAcceptMatches(payload, threadId)) {
    throw new WorldChatApiError(502, "world_chat_generation_scope_mismatch");
  }
  return payload;
}

export async function retryWorldChatResponse(
  worldId: string,
  threadId: string,
  data: { failed_request_id: string; idempotency_key: string },
): Promise<WorldChatMessageAcceptRead> {
  const payload = await requestWorldChatApi<WorldChatMessageAcceptRead>(
    worldChatApiPath(
      worldId,
      `/threads/${encodeURIComponent(threadId)}/retry`,
    ),
    { body: data, method: "POST" },
  );
  if (!worldChatMessageAcceptMatches(payload, threadId)) {
    throw new WorldChatApiError(502, "world_chat_generation_scope_mismatch");
  }
  return payload;
}

export async function getWorldChatResponseRequest(
  worldId: string,
  threadId: string,
  requestId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldChatGenerationRequestRead> {
  const payload = await requestWorldChatApi<WorldChatGenerationRequestRead>(
    worldChatApiPath(
      worldId,
      `/threads/${encodeURIComponent(threadId)}/requests/${encodeURIComponent(requestId)}`,
    ),
    { signal: options.signal },
  );
  if (!worldChatGenerationRequestMatches(payload, threadId) || payload.request_id !== requestId) {
    throw new WorldChatApiError(502, "world_chat_generation_scope_mismatch");
  }
  return payload;
}

export async function getLatestWorldChatResponseRequest(
  worldId: string,
  threadId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldChatLatestRequestRead> {
  const payload = await requestWorldChatApi<WorldChatLatestRequestRead>(
    worldChatApiPath(
      worldId,
      `/threads/${encodeURIComponent(threadId)}/requests/latest`,
    ),
    { signal: options.signal },
  );
  if (
    !payload ||
    typeof payload !== "object" ||
    !("response_request" in payload) ||
    (payload.response_request !== null &&
      !worldChatGenerationRequestMatches(payload.response_request, threadId))
  ) {
    throw new WorldChatApiError(502, "world_chat_generation_scope_mismatch");
  }
  return payload;
}

export async function streamWorldChatResponse(
  worldId: string,
  threadId: string,
  expected: WorldChatGenerationRequestRead,
  onEvent: (event: WorldChatGenerationEvent) => void | Promise<void>,
  options: { signal?: AbortSignal } = {},
): Promise<number> {
  const response = await runtimeFetch(
    `/api/backend${worldChatApiPath(
      worldId,
      `/threads/${encodeURIComponent(threadId)}/requests/${encodeURIComponent(expected.request_id)}/events`,
    )}`,
    {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/x-ndjson" },
      signal: options.signal,
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as unknown;
    throw new WorldChatApiError(
      response.status,
      errorDetail(payload, `http_${response.status}`),
    );
  }
  if (!response.body) {
    throw new WorldChatApiError(502, "world_chat_stream_missing");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastSequence = -1;
  const consumeLine = async (line: string) => {
    if (!line.trim()) return;
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      throw new WorldChatApiError(502, "world_chat_stream_invalid_json");
    }
    const event = parseGenerationEvent(value, expected);
    if (event.sequence <= lastSequence) return;
    if (event.sequence !== lastSequence + 1) {
      throw new WorldChatApiError(502, "world_chat_stream_sequence_gap");
    }
    lastSequence = event.sequence;
    await onEvent(event);
  };
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) await consumeLine(line);
    if (done) break;
  }
  if (buffer.trim()) await consumeLine(buffer);
  return lastSequence;
}

function worldChatApiPath(worldId: string, suffix: string) {
  return `/worlds/${encodeURIComponent(worldId)}/chat${suffix}`;
}

async function requestWorldChatApi<T>(
  path: string,
  options: WorldChatRequestOptions = {},
): Promise<T> {
  const { body, headers, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(headers ?? {}),
    },
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    if (response.status === 401) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new WorldChatApiError(
      response.status,
      errorDetail(payload, `http_${response.status}`),
    );
  }
  return payload as T;
}

function errorDetail(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

function worldChatThreadMatchesScope(
  value: unknown,
  worldId: string,
): value is WorldChatThreadRead {
  if (!value || typeof value !== "object") return false;
  const thread = value as Partial<WorldChatThreadRead>;
  const supportedModels = new Set<string>(
    MESSAGE_GOOGLE_GEMINI_MODELS.map((option) => option.value),
  );
  if (
    typeof thread.id !== "string" ||
    thread.world_id !== worldId ||
    !thread.requester ||
    !thread.responding ||
    thread.requester.control_mode !== "owner_controlled" ||
    thread.requester.profile_capability !== "available" ||
    thread.responding.profile_capability !== "available" ||
    typeof thread.requester.world_character_id !== "string" ||
    typeof thread.responding.world_character_id !== "string" ||
    thread.requester.world_character_id === thread.responding.world_character_id ||
    !supportedModels.has(thread.selected_model ?? "") ||
    !supportedModels.has(thread.default_model ?? "") ||
    (thread.model_binding_mode !== "default" &&
      thread.model_binding_mode !== "thread_override") ||
    (thread.model_binding_mode === "default" &&
      thread.selected_model !== thread.default_model) ||
    !Array.isArray(thread.messages) ||
    !Array.isArray(thread.evidence_summaries)
  ) {
    return false;
  }
  return (
    thread.messages.every((message) => message.thread_id === thread.id) &&
    thread.evidence_summaries.every(
      (summary) =>
        typeof summary.request_id === "string" &&
        typeof summary.assistant_message_id === "number" &&
        (summary.capability === "available" || summary.capability === "degraded") &&
        Number.isInteger(summary.count) &&
        summary.count > 0 &&
        summary.count <= 12,
    ) &&
    (!thread.latest_message || thread.latest_message.thread_id === thread.id)
  );
}

function worldChatMessageAcceptMatches(
  value: unknown,
  threadId: string,
): value is WorldChatMessageAcceptRead {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<WorldChatMessageAcceptRead>;
  return (
    (result.outcome === "accepted" || result.outcome === "replayed") &&
    !!result.user_message &&
    result.user_message.thread_id === threadId &&
    worldChatGenerationRequestMatches(result.response_request, threadId) &&
    result.response_request.user_message.id === result.user_message.id
  );
}

function worldChatGenerationRequestMatches(
  value: unknown,
  threadId: string,
): value is WorldChatGenerationRequestRead {
  if (!value || typeof value !== "object") return false;
  const request = value as Partial<WorldChatGenerationRequestRead>;
  return (
    request.protocol_version === "chat-generation-stream.v1" &&
    typeof request.request_id === "string" &&
    typeof request.request_scope_hash === "string" &&
    request.request_scope_hash.length === 64 &&
    typeof request.generation_id === "string" &&
    typeof request.attempt_number === "number" &&
    request.attempt_number >= 1 &&
    typeof request.response_slot_id === "string" &&
    typeof request.state === "string" &&
    typeof request.retryable === "boolean" &&
    typeof request.last_accepted_sequence === "number" &&
    !!request.user_message &&
    request.user_message.thread_id === threadId &&
    (!request.assistant_message || request.assistant_message.thread_id === threadId)
  );
}

function parseGenerationEvent(
  value: unknown,
  expected: WorldChatGenerationRequestRead,
): WorldChatGenerationEvent {
  if (!value || typeof value !== "object") {
    throw new WorldChatApiError(502, "world_chat_stream_event_invalid");
  }
  const event = value as Partial<WorldChatGenerationEvent>;
  if (
    event.protocol_version !== "chat-generation-stream.v1" ||
    event.request_id !== expected.request_id ||
    event.request_scope_hash !== expected.request_scope_hash ||
    event.generation_id !== expected.generation_id ||
    event.attempt_number !== expected.attempt_number ||
    !Number.isInteger(event.sequence) ||
    (event.sequence ?? -1) < 0 ||
    !["accepted", "delta", "completed", "failed", "cancelled"].includes(
      event.type ?? "",
    ) ||
    !event.payload ||
    typeof event.payload !== "object"
  ) {
    throw new WorldChatApiError(502, "world_chat_stream_event_invalid");
  }
  const payload = event.payload as Record<string, unknown>;
  const keys = Object.keys(payload).sort();
  if (
    ((event.type === "accepted" || event.type === "completed") && keys.length !== 0) ||
    (event.type === "delta" &&
      (keys.join(",") !== "text" || typeof payload.text !== "string" || !payload.text)) ||
    (event.type === "failed" &&
      (keys.join(",") !== "failure_class,retryable" ||
        typeof payload.failure_class !== "string" ||
        typeof payload.retryable !== "boolean")) ||
    (event.type === "cancelled" &&
      (keys.join(",") !== "reason" || typeof payload.reason !== "string"))
  ) {
    throw new WorldChatApiError(502, "world_chat_stream_payload_invalid");
  }
  return event as WorldChatGenerationEvent;
}
