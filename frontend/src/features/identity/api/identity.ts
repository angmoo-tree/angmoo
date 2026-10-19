import { apiRequest } from "@/features/identity/api/request";
import type { AuthRead, UserRead, UserFeedContentFilter as FeedContentFilter } from "@/lib/auth/browser-session";
import type { LocalBootstrapRead, GoogleLoginRead } from "@/features/identity/types/identity";
import { getCurrentUser, updateUserFeedPreferences } from "@/features/identity/api/session";

export function signup(data: {
  email: string;
  password: string;
  display_name: string;
  privacy_policy_agreed: boolean;
  terms_agreed: boolean;
  turnstile_token?: string;
}) {
  return apiRequest<AuthRead>("/auth/signup", {
    method: "POST",
    body: data,
  });
}

export function getLocalBootstrapStatus() {
  return apiRequest<LocalBootstrapRead>("/auth/local/bootstrap", {
    suppressAuthFailureEvent: true,
  });
}

export function createLocalBootstrapChallenge() {
  return apiRequest<{ expires_at: string }>("/auth/local/bootstrap/challenge", {
    method: "POST",
  });
}

export function login(data: { email: string; password: string }) {
  return apiRequest<AuthRead>("/auth/login", {
    method: "POST",
    body: data,
  });
}

export function logoutCurrentSession() {
  return apiRequest<void>("/auth/logout", {
    method: "POST",
  });
}

export function googleLogin(data: { credential: string }) {
  return apiRequest<GoogleLoginRead>("/auth/google", {
    method: "POST",
    body: data,
  });
}

export function completeGoogleSignup(data: {
  display_name: string;
  privacy_policy_agreed: boolean;
  terms_agreed: boolean;
  turnstile_token?: string;
}) {
  return apiRequest<AuthRead>("/auth/google/complete", {
    method: "POST",
    body: data,
    anonymous: false,
  });
}

export function linkGoogleAccount(data: { credential: string }) {
  return apiRequest<AuthRead>("/auth/google/link", {
    method: "POST",
    body: data,
  });
}

export function getMe(options: { suppressAuthFailureEvent?: boolean } = {}) {
  return getCurrentUser(options);
}

export function updateMe(data: {
  display_name: string;
  privacy_policy_agreed?: boolean;
  terms_agreed?: boolean;
}) {
  return apiRequest<UserRead>("/auth/me", {
    method: "PATCH",
    body: data,
  });
}

export function updateInstallationLabel(local_label: string) {
  return apiRequest<{ local_label: string | null }>("/auth/local/installation", {
    method: "PATCH", body: { local_label },
  });
}

export function updateMePreferences(data: { feed_content_filter: FeedContentFilter }) {
  return updateUserFeedPreferences(data);
}

export function deleteCurrentAccount(data: { confirmation: string }) {
  return apiRequest<void>("/auth/me", {
    method: "DELETE",
    body: data,
  });
}
