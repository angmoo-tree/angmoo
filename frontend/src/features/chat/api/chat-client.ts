import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";

import type {
  CharacterMessageSettingRead,
  MessageCredentialSource,
  MessageGoogleGeminiModel,
  MessageSendRead,
  MessageSettingsRead,
  MessageThreadListRead,
  MessageThreadRead,
} from "../model/chat-contract";

type ChatRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

export function listMessageThreads() {
  return requestChatApi<MessageThreadListRead>("/messages/threads");
}

export function createMessageThread(data: {
  character_id: string;
  selected_model?: MessageGoogleGeminiModel;
}) {
  return requestChatApi<MessageThreadRead>("/messages/threads", {
    method: "POST",
    body: data,
  });
}

export function getMessageThread(threadId: string) {
  return requestChatApi<MessageThreadRead>("/messages/threads/" + threadId);
}

export function updateMessageThread(
  threadId: string,
  data: { selected_model: MessageGoogleGeminiModel },
) {
  return requestChatApi<MessageThreadRead>("/messages/threads/" + threadId, {
    method: "PATCH",
    body: data,
  });
}

export function deleteMessageThread(threadId: string) {
  return requestChatApi<void>("/messages/threads/" + threadId, {
    method: "DELETE",
  });
}

export function sendThreadMessage(threadId: string, content: string) {
  return requestChatApi<MessageSendRead>(
    "/messages/threads/" + threadId + "/messages",
    { method: "POST", body: { content } },
  );
}

export function retryThreadMessage(threadId: string, messageId: number) {
  return requestChatApi<MessageSendRead>(
    "/messages/threads/" + threadId + "/messages/" + messageId + "/retry",
    { method: "POST" },
  );
}

export function getMessageSettings() {
  return requestChatApi<MessageSettingsRead>("/messages/settings");
}

export function updateMessageSettings(data: {
  credential_source?: MessageCredentialSource;
  source_character_id?: string | null;
  default_model?: MessageGoogleGeminiModel;
  api_key?: string;
  clear_message_key?: boolean;
}) {
  return requestChatApi<MessageSettingsRead>("/messages/settings", {
    method: "PATCH",
    body: data,
  });
}

export function getCharacterMessageSettings(characterId: string) {
  return requestChatApi<CharacterMessageSettingRead>(
    "/characters/" + characterId + "/message-settings",
  );
}

export function updateCharacterMessageSettings(
  characterId: string,
  data: { enabled: boolean },
) {
  return requestChatApi<CharacterMessageSettingRead>(
    "/characters/" + characterId + "/message-settings",
    { method: "PATCH", body: data },
  );
}

async function requestChatApi<T>(
  path: string,
  options: ChatRequestOptions = {},
) {
  const { body, headers, ...rest } = options;
  const response = await runtimeFetch("/api/backend" + path, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
  });

  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (error) {
    if (!response.ok) {
      throw new Error(
        htmlErrorMessage(text) ??
          (text.trim() || "Request failed with " + response.status),
      );
    }
    throw error;
  }

  if (!response.ok) {
    if (response.status === 401) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new Error(
      getErrorMessage(payload, "Request failed with " + response.status),
    );
  }

  return payload as T;
}

function getErrorMessage(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    Array.isArray(payload.detail)
  ) {
    const first = payload.detail.find(
      (item) => item && typeof item === "object",
    );
    if (first && typeof first === "object" && "msg" in first) {
      return typeof first.msg === "string" ? first.msg : fallback;
    }
  }
  return fallback;
}

function htmlErrorMessage(text: string) {
  const trimmed = text.trim().toLowerCase();
  if (!trimmed.startsWith("<!doctype html") && !trimmed.startsWith("<html")) {
    return null;
  }
  return "요청 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
}
