import { notifyAuthChanged, removeLegacyAuthTokens } from "@/lib/auth/browser-session";
import type { GoogleLoginRead, PendingGoogleSignup } from "@/features/identity/types/identity";

const USER_KEY = "angmoo.user";
const PENDING_GOOGLE_SIGNUP_KEY = "angmoo.pendingGoogleSignup";

export function getPendingGoogleSignup(): PendingGoogleSignup | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(PENDING_GOOGLE_SIGNUP_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PendingGoogleSignup>;
    if (
      typeof parsed.expires_at !== "string" ||
      typeof parsed.email !== "string"
    ) {
      return null;
    }
    return {
      expires_at: parsed.expires_at,
      email: parsed.email,
    };
  } catch {
    return null;
  }
}

export function hasPendingGoogleSignup() {
  return Boolean(getPendingGoogleSignup());
}

export function storePendingGoogleSignup(auth: GoogleLoginRead) {
  if (!auth.expires_at || !auth.email) {
    throw new Error("Google signup information is missing.");
  }
  window.sessionStorage.setItem(
    PENDING_GOOGLE_SIGNUP_KEY,
    JSON.stringify({
      expires_at: auth.expires_at,
      email: auth.email,
    }),
  );
  window.sessionStorage.removeItem(USER_KEY);
  removeLegacyAuthTokens();
  window.localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
}

export function clearPendingGoogleSignup() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  notifyAuthChanged();
}
