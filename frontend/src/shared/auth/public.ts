export { AuthProvider } from "@/composition/providers/auth-provider";
export { useAuth } from "@/hooks/use-auth";
export {
  AUTH_CHANGED_EVENT,
  cacheUser,
  clearLegacyAuthStorage,
  clearStoredUser,
  getCurrentUser,
  getStoredUser,
  isAuthError,
  issueLocalSession,
  notifyAuthChanged,
  storeUser,
  updateUserFeedPreferences,
} from "./auth-session";
export type {
  AuthRead,
  UserFeedContentFilter,
  UserRead,
} from "./auth-session";
