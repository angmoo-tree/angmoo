"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useRef,
  type ReactNode,
} from "react";

import { AUTH_CHANGED_EVENT, cacheUser, clearLegacyAuthStorage, clearStoredUser, isAuthError, type UserRead } from "@/lib/auth/browser-session";
import { getCurrentUser, issueLocalSession } from "@/features/identity/api/session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, RuntimeFetchError } from "@/lib/runtime/runtime-config";

import { AuthContext, type AuthStatus } from "@/lib/auth/auth-context";
import { UserEnvironmentProvider } from "@/composition/providers/user-environment-provider";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [user, setUser] = useState<UserRead | null>(null);
  const [sessionRevision, setSessionRevision] = useState(0);
  const refreshSequence = useRef(0);

  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    try {
      const currentUser = await getCurrentUser({
        suppressAuthFailureEvent: true,
      });
      if (sequence !== refreshSequence.current) return;
      cacheUser(currentUser);
      setUser(currentUser);
      setStatus("authenticated");
    } catch (error) {
      if (sequence !== refreshSequence.current) return;
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
        if (sequence !== refreshSequence.current) return;
        setSessionRevision(value => value + 1);
        cacheUser(auth.user);
        setUser(auth.user);
        setStatus("authenticated");
      } catch {
        if (sequence !== refreshSequence.current) return;
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
      setUser(null);
      setSessionRevision(value => value + 1);
      setStatus("checking");
      void refresh();
    };
    window.addEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
    window.addEventListener(
      DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
      handleRuntimeConfigChanged,
    );
    return () => {
      refreshSequence.current += 1;
      window.clearTimeout(refreshId);
      window.removeEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
      window.removeEventListener(
        DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
        handleRuntimeConfigChanged,
      );
    };
  }, [refresh]);

  const value = useMemo(
    () => ({ status, user, refresh, sessionRevision }),
    [refresh, status, user, sessionRevision],
  );

  return <AuthContext.Provider value={value}><UserEnvironmentProvider>{children}</UserEnvironmentProvider></AuthContext.Provider>;
}

