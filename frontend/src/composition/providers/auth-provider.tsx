"use client";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { AUTH_CHANGED_EVENT, cacheUser, clearLegacyAuthStorage, clearStoredUser } from "@/lib/auth/browser-session";
import { AuthContext, type AuthStatus } from "@/lib/auth/auth-context";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { detectPreferredLanguage } from "@/lib/i18n/detection";
import { createLocalEntryController } from "@/features/identity/controllers/local-entry-controller";
import { LocalEntryContext } from "@/features/identity/controllers/local-entry-context";
import { connectionStore } from "@/features/identity/controllers/local-connection-store";
import { createLocalEntryApi } from "@/features/identity/api/local-entry";
import { UserEnvironmentProvider } from "@/composition/providers/user-environment-provider";
import { WorldNotificationProvider } from "@/features/social/hooks/world-notification-context";

const makeController = () => {
  const requests = new AbortController();
  return createLocalEntryController({ api: createLocalEntryApi(requests.signal), store: connectionStore,
    language: detectPreferredLanguage, abort: () => requests.abort(),
    onUser: user => { if (user) cacheUser(user); else clearStoredUser(); } });
};
export function AuthProvider({ children }: { children: ReactNode }) {
  const [controller, setController] = useState(makeController);
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [sessionRevision, setSessionRevision] = useState(0);
  const refresh = useCallback(() => controller.refresh(), [controller]);
  const status: AuthStatus = snapshot.phase === "authenticated" ? "authenticated"
    : ["checking", "preparing", "ending"].includes(snapshot.phase) ? "checking" : "unauthenticated";
  useEffect(() => {
    clearLegacyAuthStorage();
    void refresh();
    const changed = () => { void refresh(); };
    const runtimeChanged = () => {
      controller.invalidate();
      clearStoredUser();
      setSessionRevision(value => value + 1);
      setController(makeController());
    };
    const unsubscribe = connectionStore.subscribe(changed);
    window.addEventListener(AUTH_CHANGED_EVENT, changed);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, runtimeChanged);
    return () => {
      unsubscribe();
      window.removeEventListener(AUTH_CHANGED_EVENT, changed);
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, runtimeChanged);
    };
  }, [controller, refresh]);
  const revision = sessionRevision + snapshot.sessionRevision;
  const value = useMemo(() => ({ status, user: snapshot.user, refresh, sessionRevision: revision }), [status, snapshot.user, refresh, revision]);
  const entry = useMemo(() => ({ controller, snapshot }), [controller, snapshot]);
  return <AuthContext.Provider value={value}><LocalEntryContext.Provider value={entry}><UserEnvironmentProvider><WorldNotificationProvider>{children}</WorldNotificationProvider></UserEnvironmentProvider></LocalEntryContext.Provider></AuthContext.Provider>;
}
