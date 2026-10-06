import { apiRequest } from "@/features/identity/api/request";
import { authRequest, type UserRead } from "@/lib/auth/browser-session";
import type { UserEnvironment, UiLanguage } from "@/types/user-environment";

export function getUserEnvironment(signal?: AbortSignal) {
  return apiRequest<UserEnvironment>("/auth/local/environment", { signal });
}

export function synchronizeUserEnvironment(data: { client_id: string; lease_token: string | null;
  expected_revision: number; sequence: number; preferred_language: string | null; timezone: string | null }, signal?: AbortSignal) {
  return apiRequest<UserEnvironment>("/auth/local/environment", { method: "POST", body: data, signal });
}

export function saveUiLanguage(ui_language: UiLanguage, expected_ui_revision: number) {
  return authRequest<UserRead>("/auth/me/preferences", { method: "PATCH", body: { ui_language, expected_ui_revision } });
}
