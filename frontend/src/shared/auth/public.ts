export { AuthProvider } from "@/composition/providers/auth-provider";
export { useAuth } from "@/hooks/use-auth";
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
export type {
  AuthRead,
  UserFeedContentFilter,
  UserRead,
} from "@/lib/auth/browser-session";
