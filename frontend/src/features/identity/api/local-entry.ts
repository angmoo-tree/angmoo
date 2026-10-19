import { authRequest, type AuthRead, type UserRead } from "@/lib/auth/browser-session";
import type { LocalBootstrapRead } from "../types/identity";
import type { LocalClientRequest, LocalClientState } from "../types/local-entry";

export function createLocalEntryApi(signal?: AbortSignal) {
const options = { suppressAuthFailureEvent: true, signal };
return {
  bootstrap: () => authRequest<LocalBootstrapRead>("/auth/local/bootstrap", options),
  currentUser: () => authRequest<UserRead>("/auth/me", options),
  challenge: () => authRequest<{ expires_at: string }>("/auth/local/bootstrap/challenge", { ...options, method: "POST" }),
  status: (data: LocalClientRequest) => authRequest<LocalClientState>(`/auth/local/client?${new URLSearchParams(Object.entries(data).map(([key, value]) => [key, String(value)]))}`, options),
  prepare: (data: LocalClientRequest, preferred_language: string | null) => authRequest<AuthRead>("/auth/local/bootstrap/prepare", { ...options, method: "POST", body: { ...data, preferred_language } }),
  claim: (data: LocalClientRequest, owner_user_id: string) => authRequest<AuthRead>("/auth/local/bootstrap/claim", { ...options, method: "POST", body: { ...data, owner_user_id } }),
  issue: (data: LocalClientRequest) => authRequest<AuthRead>("/auth/local/session", { ...options, method: "POST", body: data }),
  stop: (data: LocalClientRequest) => authRequest<LocalClientState>("/auth/local/client/stop", { ...options, method: "POST", body: data }),
  resume: (data: LocalClientRequest) => authRequest<AuthRead | LocalClientState>("/auth/local/client/resume", { ...options, method: "POST", body: data }),
};
}
export const localEntryApi = createLocalEntryApi();
