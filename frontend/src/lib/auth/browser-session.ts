import { ApiRequestError } from "@/lib/http/error-contract";
import { runtimeFetch } from "@/lib/runtime/runtime-config";

export type UserFeedContentFilter = "all" | "posts" | "reposts";

export type UserRead = {
  id: string;
  email: string | null;
  display_name: string;
  display_name_updated_at: string | null;
  display_name_change_available_at: string | null;
  profile_setup_completed: boolean;
  feed_content_filter: UserFeedContentFilter;
  ui_language?: "ko" | "en" | null;
  ui_preference_revision?: number;
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

let sessionRevision = 0;

// A response belongs to the session and runtime that admitted its request.
// The launch token stays in memory and is never exposed in an error or log.
export function captureAuthRequestScope() {
  const runtime = typeof window === "undefined" ? null : window.__ANGMOO_RUNTIME_CONFIG__;
  return {
    revision: sessionRevision,
    userId: getStoredUser()?.id ?? null,
    apiBaseUrl: runtime?.apiBaseUrl,
    launchToken: runtime?.launchToken,
  };
}

export function isCurrentAuthRequestScope(scope: ReturnType<typeof captureAuthRequestScope>) {
  const current = captureAuthRequestScope();
  return scope.revision === current.revision && scope.userId === current.userId
    && scope.apiBaseUrl === current.apiBaseUrl && scope.launchToken === current.launchToken;
}

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
    ui_language: user.ui_language === "ko" || user.ui_language === "en" ? user.ui_language : null,
    ui_preference_revision: typeof user.ui_preference_revision === "number" ? user.ui_preference_revision : 0,
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
  if (getStoredUser()?.id !== user.id) sessionRevision += 1;
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  if (user.profile_setup_completed) {
    window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  }
  window.localStorage.removeItem(USER_KEY);
}

export function clearStoredUser() {
  if (typeof window === "undefined") return;
  sessionRevision += 1;
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
  if (error instanceof ApiRequestError) return error.status === 401;
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

export async function authRequest<T>(
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
  const scope = captureAuthRequestScope();
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
      throw new ApiRequestError("The request could not be completed. Please try again.", response.status, null);
    }
    throw error;
  }
  if (!response.ok) {
    if (response.status === 401 && !anonymous && !suppressAuthFailureEvent
        && !rest.signal?.aborted && isCurrentAuthRequestScope(scope)) {
      clearStoredUser();
      notifyAuthChanged();
    }
    const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    const code = typeof detail === "string" && /^[a-z][a-z0-9_]{0,80}$/.test(detail) ? detail : null;
    throw new ApiRequestError(response.status === 401 ? "Please sign in again." : "The request could not be completed. Please try again.", response.status, code, {}, response.headers.get("Retry-After"));
  }
  return payload as T;
}

export function storeAuth(auth: AuthRead) {
  sessionRevision += 1;
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(auth.user));
  window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  removeLegacyAuthTokens();
  window.localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
}

export function clearAuth() {
  clearStoredUser();
  window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  removeLegacyAuthTokens();
  window.localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
}

export function removeLegacyAuthTokens() {
  window.sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  window.localStorage.removeItem(LEGACY_TOKEN_KEY);
}
