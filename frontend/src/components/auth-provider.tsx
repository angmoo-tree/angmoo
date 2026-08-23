"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  AUTH_CHANGED_EVENT,
  cacheUser,
  clearLegacyAuthStorage,
  clearStoredUser,
  getMe,
  isAuthError,
  issueLocalSession,
  type UserRead,
} from "@/lib/agents";
import {
  DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
  RuntimeFetchError,
} from "@/shared/runtime/public";

type AuthStatus = "checking" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: AuthStatus;
  user: UserRead | null;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [user, setUser] = useState<UserRead | null>(null);

  const refresh = useCallback(async () => {
    try {
      const currentUser = await getMe({ suppressAuthFailureEvent: true });
      cacheUser(currentUser);
      setUser(currentUser);
      setStatus("authenticated");
    } catch (error) {
      if (error instanceof RuntimeFetchError) {
        // A packaged WebView can mount before DesktopRuntimeGate has received
        // the sidecar endpoint and launch token. That transient startup state
        // is not an authentication failure: keeping it as `checking` prevents
        // a newly opened Studio/Relationship window from replacing its exact
        // product route with `/login` before runtime metadata arrives.
        setStatus("checking");
        return;
      }
      if (!isAuthError(error)) {
        setStatus((current) =>
          current === "checking" ? "unauthenticated" : current,
        );
        return;
      }
      clearStoredUser();
      try {
        const auth = await issueLocalSession();
        cacheUser(auth.user);
        setUser(auth.user);
        setStatus("authenticated");
      } catch {
        setUser(null);
        setStatus("unauthenticated");
      }
    }
  }, []);

  useEffect(() => {
    clearLegacyAuthStorage();
    const refreshId = window.setTimeout(() => {
      void refresh();
    }, 0);
    const handleAuthChanged = () => {
      void refresh();
    };
    const handleRuntimeConfigChanged = () => {
      // Change state synchronously. The child product route can otherwise
      // observe the previous unauthenticated state while the async refresh is
      // still issuing/reusing the local-owner session.
      setStatus("checking");
      void refresh();
    };
    window.addEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
    window.addEventListener(
      DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
      handleRuntimeConfigChanged,
    );
    return () => {
      window.clearTimeout(refreshId);
      window.removeEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
      window.removeEventListener(
        DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
        handleRuntimeConfigChanged,
      );
    };
  }, [refresh]);

  const value = useMemo(
    () => ({ status, user, refresh }),
    [refresh, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
