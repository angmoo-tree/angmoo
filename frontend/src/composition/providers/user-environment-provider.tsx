"use client";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/http/api-request";
import { createUiI18n, resolveUiLanguage } from "@/lib/i18n/instance";
import { detectPreferredLanguage, detectUserEnvironment } from "@/lib/i18n/detection";
import { EnvironmentContext } from "@/lib/i18n/environment-context";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { getUserEnvironment, synchronizeUserEnvironment } from "@/features/identity/api/environment";
import { uiResources } from "@/composition/providers/ui-resources";
import { synchronizeEnvironment } from "@/composition/providers/environment-synchronization";
import type { UserEnvironment } from "@/types/user-environment";

// Browser preference is display-only. Authentication still owns persistence,
// the environment lease and readiness for new default content.
function subscribeToUiLanguage(changed: () => void) {
  window.addEventListener("languagechange", changed);
  window.addEventListener("focus", changed);
  document.addEventListener("visibilitychange", changed);
  return () => {
    window.removeEventListener("languagechange", changed);
    window.removeEventListener("focus", changed);
    document.removeEventListener("visibilitychange", changed);
  };
}

function serverUiLanguage() { return null; }

export function UserEnvironmentProvider({ children }: { children: ReactNode }) {
  const { status, user, sessionRevision = 0 } = useAuth();
  const userId = user?.id;
  const [i18n] = useState(() => createUiI18n(uiResources));
  const [environment, setEnvironment] = useState<UserEnvironment | null>(null);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState<{ scope: string; code: string } | null>(null);
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  const [environmentScope, setEnvironmentScope] = useState("");
  const [retryRevision, setRetryRevision] = useState(0);
  const retry = useCallback(() => setRetryRevision(value => value + 1), []);
  const currentScope = `${userId ?? ""}:${runtimeRevision}:${sessionRevision}`;
  const detectedUiLanguage = useSyncExternalStore(subscribeToUiLanguage, detectPreferredLanguage, serverUiLanguage);

  useEffect(() => {
    const changed = () => { setReady(false); setEnvironment(null); setRuntimeRevision(value => value + 1); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
  }, []);

  useEffect(() => {
    if (status !== "authenticated" || !userId) return;
    const controller = new AbortController();
    const clientId = crypto.randomUUID();
    const lease = { clientId, token: null as string | null, sequence: 0 };
    let active = true;
    let busy = false;
    let lastStarted = -Infinity;
    let pending = false;
    let followup: ReturnType<typeof setTimeout> | undefined;
    let round: AbortController | undefined;
    let lastDetected: ReturnType<typeof detectUserEnvironment> | null = null;
    const schedule = () => {
      if (followup === undefined && active) followup = setTimeout(() => {
        followup = undefined;
        void synchronize();
      }, Math.max(0, 250 - (performance.now() - lastStarted)));
    };
    const synchronize = async () => {
      if (!active || document.visibilityState !== "visible") return;
      if (busy) { pending = true; return; }
      if (performance.now() - lastStarted < 250) { schedule(); return; }
      busy = true;
      pending = false;
      let succeeded = false;
      lastStarted = performance.now();
      const currentRound = new AbortController();
      round = currentRound;
      const abortRound = () => currentRound.abort();
      controller.signal.addEventListener("abort", abortRound, { once: true });
      try {
        const current = await synchronizeEnvironment(lease, { read: getUserEnvironment,
          write: synchronizeUserEnvironment, detect: () => {
            lastDetected = detectUserEnvironment();
            return lastDetected;
          } }, currentRound.signal);
        succeeded = true;
        if (active) { setEnvironment(current); setEnvironmentScope(`${userId}:${runtimeRevision}:${sessionRevision}`); setReady(true); setFailure(null); }
      } catch (error) {
        if (active && !currentRound.signal.aborted && !controller.signal.aborted) {
          setReady(false);
          setFailure({ scope: `${userId}:${runtimeRevision}:${sessionRevision}`,
            code: error instanceof ApiRequestError ? error.code ?? "environment_sync_failed" : "environment_sync_failed" });
        }
      } finally {
        controller.signal.removeEventListener("abort", abortRound);
        round = undefined;
        busy = false;
        // Merge events during a request, but never turn a failed bounded
        // round into an unbounded immediate retry loop.
        if (active && pending && document.visibilityState === "visible" &&
            (currentRound.signal.aborted || (succeeded && JSON.stringify(lastDetected) !== JSON.stringify(detectUserEnvironment())))) schedule();
        pending = false;
      }
    };
    void synchronize();
    const refresh = () => {
      if (document.visibilityState === "hidden") {
        round?.abort(); pending = false;
        if (followup !== undefined) { clearTimeout(followup); followup = undefined; }
      } else void synchronize();
    };
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener("focus", refresh);
    window.addEventListener("languagechange", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      active = false; controller.abort(); window.clearInterval(timer);
      if (followup !== undefined) clearTimeout(followup);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("languagechange", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [status, userId, runtimeRevision, sessionRevision, retryRevision]);

  const scopedEnvironment = environmentScope === currentScope ? environment : null;
  const errorCode = status === "authenticated" && failure?.scope === currentScope ? failure.code : null;
  const language = resolveUiLanguage(user?.ui_language, scopedEnvironment?.preferred_language ?? detectedUiLanguage ?? undefined);
  useEffect(() => { void i18n.changeLanguage(language); document.documentElement.lang = language; }, [i18n, language]);
  const value = useMemo(() => ({ environment: status === "authenticated" ? scopedEnvironment : null,
    ready: status === "authenticated" && ready && environmentScope === currentScope, errorCode, retry }),
    [scopedEnvironment, ready, errorCode, status, environmentScope, currentScope, retry]);
  return <I18nextProvider i18n={i18n}><EnvironmentContext.Provider value={value}>{children}</EnvironmentContext.Provider></I18nextProvider>;
}
