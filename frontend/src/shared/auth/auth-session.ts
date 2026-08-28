import { runtimeFetch } from "@/shared/runtime/public";

export type UserFeedContentFilter = "all" | "posts" | "reposts";

export type UserRead = {
  id: string;
  email: string | null;
  display_name: string;
  display_name_updated_at: string | null;
  display_name_change_available_at: string | null;
  profile_setup_completed: boolean;
  feed_content_filter: UserFeedContentFilter;
  is_admin: boolean;
};

export type AuthRead = {
  user: UserRead;
  profile_setup_required: boolean;
};

type AuthRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  anonymous?: boolean;
  suppressAuthFailureEvent?: boolean;
};

const LEGACY_TOKEN_KEY = ["angmoo", "authToken"].join(".");
const USER_KEY = "angmoo.user";
const PENDING_GOOGLE_SIGNUP_KEY = "angmoo.pendingGoogleSignup";

export const AUTH_CHANGED_EVENT = "angmoo:auth-changed";

export function getStoredUser(): UserRead | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return normalizeStoredUser(JSON.parse(raw));
  } catch {
    return null;
  }
}

function normalizeStoredUser(value: unknown): UserRead | null {
  if (!value || typeof value !== "object") return null;
  const user = value as Partial<UserRead>;
  if (typeof user.id !== "string" || typeof user.display_name !== "string") {
    return null;
  }
  return {
    id: user.id,
    email: typeof user.email === "string" ? user.email : null,
    display_name: user.display_name,
    display_name_updated_at:
      typeof user.display_name_updated_at === "string"
        ? user.display_name_updated_at
        : null,
    display_name_change_available_at:
      typeof user.display_name_change_available_at === "string"
        ? user.display_name_change_available_at
        : null,
    profile_setup_completed:
      typeof user.profile_setup_completed === "boolean"
        ? user.profile_setup_completed
        : true,
    feed_content_filter: normalizeFeedContentFilter(user.feed_content_filter),
    is_admin: user.is_admin === true,
  };
}

function normalizeFeedContentFilter(value: unknown): UserFeedContentFilter {
  if (value === "posts" || value === "reposts" || value === "all") {
    return value;
  }
  return "all";
}

export function notifyAuthChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function storeUser(user: UserRead) {
  cacheUser(user);
  notifyAuthChanged();
}

export function cacheUser(user: UserRead) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  if (user.profile_setup_completed) {
    window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  }
  window.localStorage.removeItem(USER_KEY);
}

export function clearStoredUser() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(USER_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function clearLegacyAuthStorage() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  window.localStorage.removeItem(LEGACY_TOKEN_KEY);
  const pending = window.sessionStorage.getItem(PENDING_GOOGLE_SIGNUP_KEY);
  if (pending?.includes(["pending", "token"].join("_"))) {
    window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  }
}

export function isAuthError(error: unknown) {
  if (!(error instanceof Error)) return false;
  const message = error.message.trim();
  return (
    message === "Authorization required" ||
    message === "Invalid token" ||
    message === "Bearer token required" ||
    message === "Invalid or expired token" ||
    message === "Invalid or expired signup token" ||
    message === "Not authenticated" ||
    message === "401" ||
    message.includes("401")
  );
}

export function getCurrentUser(
  options: { suppressAuthFailureEvent?: boolean } = {},
) {
  return authRequest<UserRead>("/auth/me", options);
}

export function issueLocalSession() {
  return authRequest<AuthRead>("/auth/local/session", { method: "POST" });
}

export function updateUserFeedPreferences(data: {
  feed_content_filter: UserFeedContentFilter;
}) {
  return authRequest<UserRead>("/auth/me/preferences", {
    method: "PATCH",
    body: data,
  });
}

async function authRequest<T>(
  path: string,
  options: AuthRequestOptions = {},
) {
  const {
    body,
    headers,
    anonymous = false,
    suppressAuthFailureEvent = false,
    ...rest
  } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
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
          (text.trim() || `Request failed with ${response.status}`),
      );
    }
    throw error;
  }
  if (!response.ok) {
    if (response.status === 401 && !anonymous && !suppressAuthFailureEvent) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new Error(errorMessage(payload, `Request failed with ${response.status}`));
  }
  return payload as T;
}

function errorMessage(payload: unknown, fallback: string) {
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

function htmlErrorMessage(text: string) {
  const trimmed = text.trim().toLowerCase();
  if (!trimmed.startsWith("<!doctype html") && !trimmed.startsWith("<html")) {
    return null;
  }
  return "요청 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
}
