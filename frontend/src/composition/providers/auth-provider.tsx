"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { AUTH_CHANGED_EVENT, cacheUser, clearLegacyAuthStorage, clearStoredUser, isAuthError, type UserRead } from "@/lib/auth/browser-session";
import { getCurrentUser, issueLocalSession } from "../../shared/auth/auth-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, RuntimeFetchError } from "@/lib/runtime/runtime-config";

import { AuthContext, type AuthStatus } from "@/lib/auth/auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [user, setUser] = useState<UserRead | null>(null);

  const refresh = useCallback(async () => {
    try {
      const currentUser = await getCurrentUser({
        suppressAuthFailureEvent: true,
      });
      cacheUser(currentUser);
      setUser(currentUser);
      setStatus("authenticated");
    } catch (error) {
      if (error instanceof RuntimeFetchError) {
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

