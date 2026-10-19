import {
  authRequest,
  type UserRead,
  type UserFeedContentFilter,
} from "@/lib/auth/browser-session";

export {
  AUTH_CHANGED_EVENT,
  cacheUser,
  clearLegacyAuthStorage,
  clearStoredUser,
  getStoredUser,
  isAuthError,
  notifyAuthChanged,
  storeUser,
} from "@/lib/auth/browser-session";
export type { AuthRead, UserRead, UserFeedContentFilter } from "@/lib/auth/browser-session";

export function getCurrentUser(
  options: { suppressAuthFailureEvent?: boolean } = {},
) {
  return authRequest<UserRead>("/auth/me", options);
}

export function updateUserFeedPreferences(data: {
  feed_content_filter: UserFeedContentFilter;
}) {
  return authRequest<UserRead>("/auth/me/preferences", {
    method: "PATCH",
    body: data,
  });
}
