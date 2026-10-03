"use client";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/http/api-request";
import { createUiI18n, resolveUiLanguage } from "@/lib/i18n/instance";
import { detectUserEnvironment } from "@/lib/i18n/detection";
import { EnvironmentContext } from "@/lib/i18n/environment-context";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { getUserEnvironment, synchronizeUserEnvironment } from "@/features/identity/api/environment";
import { uiResources } from "@/composition/providers/ui-resources";
import type { UserEnvironment } from "@/types/user-environment";

export function UserEnvironmentProvider({ children }: { children: ReactNode }) {
  const { status, user, sessionRevision = 0 } = useAuth();
  const userId = user?.id;
  const [i18n] = useState(() => createUiI18n(uiResources));
  const [environment, setEnvironment] = useState<UserEnvironment | null>(null);
  const [ready, setReady] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  const [environmentScope, setEnvironmentScope] = useState("");
  const currentScope = `${userId ?? ""}:${runtimeRevision}:${sessionRevision}`;

  useEffect(() => {
    const changed = () => { setReady(false); setEnvironment(null); setRuntimeRevision(value => value + 1); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
  }, []);

  useEffect(() => {
    if (status !== "authenticated" || !userId) return;
    const controller = new AbortController();
    const clientId = crypto.randomUUID();
    let leaseToken: string | null = null;
    let sequence = 0;
    let active = true;
    let busy = false;
    let current: UserEnvironment | null = null;
    const synchronize = async () => {
      if (!active || busy || document.visibilityState !== "visible") return;
      busy = true;
      try {
        current = await getUserEnvironment(controller.signal);
        const detected = detectUserEnvironment();
        if (detected.preferred_language || detected.timezone) {
          try {
            current = await synchronizeUserEnvironment({ client_id: clientId, lease_token: leaseToken,
              expected_revision: current.environment_revision, sequence: ++sequence, ...detected }, controller.signal);
            leaseToken = current.lease_token ?? leaseToken;
          } catch (error) {
            if (!(error instanceof ApiRequestError) || error.status !== 409) throw error;
            leaseToken = null;
            current = await getUserEnvironment(controller.signal);
          }
        }
        if (active) { setEnvironment(current); setEnvironmentScope(`${userId}:${runtimeRevision}:${sessionRevision}`); setReady(true); setErrorCode(null); }
      } catch (error) {
        if (active && !controller.signal.aborted) {
          setErrorCode(error instanceof ApiRequestError ? error.code ?? "environment_sync_failed" : "environment_sync_failed");
        }
      } finally { busy = false; }
    };
    void synchronize();
    const refresh = () => { void synchronize(); };
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener("focus", refresh);
    window.addEventListener("languagechange", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      active = false; controller.abort(); window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("languagechange", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [status, userId, runtimeRevision, sessionRevision]);

  const scopedEnvironment = environmentScope === currentScope ? environment : null;
  const language = resolveUiLanguage(user?.ui_language, scopedEnvironment?.preferred_language);
  useEffect(() => { void i18n.changeLanguage(language); document.documentElement.lang = language; }, [i18n, language]);
  const value = useMemo(() => ({ environment: status === "authenticated" ? scopedEnvironment : null,
    ready: status === "authenticated" && ready && environmentScope === currentScope, errorCode }),
    [scopedEnvironment, ready, errorCode, status, environmentScope, currentScope]);
  return <I18nextProvider i18n={i18n}><EnvironmentContext.Provider value={value}>{children}</EnvironmentContext.Provider></I18nextProvider>;
}
