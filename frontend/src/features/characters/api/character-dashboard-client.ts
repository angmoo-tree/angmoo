import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";

import type { CharacterDashboardItem } from "../model/character-dashboard-contract";
import { notifyCharactersChanged } from "../model/character-dashboard-session";

type CharacterRequestOptions = Omit<RequestInit, "body" | "credentials"> & {
  body?: unknown;
};

export function listCharacterDashboardItems() {
  return requestCharacterApi<CharacterDashboardItem[]>("/agents");
}

export async function activateCharacterAutonomy(characterId: string) {
  const result = await requestCharacterApi<CharacterDashboardItem>(
    `/agents/${encodeURIComponent(characterId)}/activate`,
    { method: "POST" },
  );
  notifyCharactersChanged();
  return result;
}

export async function deactivateCharacterAutonomy(characterId: string) {
  const result = await requestCharacterApi<CharacterDashboardItem>(
    `/agents/${encodeURIComponent(characterId)}/deactivate`,
    { method: "POST" },
  );
  notifyCharactersChanged();
  return result;
}

async function requestCharacterApi<T>(
  path: string,
  options: CharacterRequestOptions = {},
) {
  const { body, headers, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
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
    if (response.ok) throw error;
  }
  if (!response.ok) {
    if (response.status === 401) {
      clearStoredUser();
      notifyAuthChanged();
    }
    const detail =
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `http_${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}
