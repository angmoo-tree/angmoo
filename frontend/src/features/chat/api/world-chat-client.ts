import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";

import type {
  WorldChatThreadCreate,
  WorldChatThreadCreateRead,
  WorldChatThreadListRead,
  WorldChatThreadRead,
} from "../model/world-chat-contract";

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
  if (
    typeof thread.id !== "string" ||
    thread.world_id !== worldId ||
    !thread.requester ||
    !thread.responding ||
    thread.requester.control_mode !== "owner_controlled" ||
    typeof thread.requester.world_character_id !== "string" ||
    typeof thread.responding.world_character_id !== "string" ||
    thread.requester.world_character_id === thread.responding.world_character_id ||
    !Array.isArray(thread.messages)
  ) {
    return false;
  }
  return (
    thread.messages.every((message) => message.thread_id === thread.id) &&
    (!thread.latest_message || thread.latest_message.thread_id === thread.id)
  );
}
