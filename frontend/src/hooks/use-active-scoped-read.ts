"use client";

import { useEffect, useState } from "react";
import { useAuth } from "./use-auth";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";

/** A cancellable read lifetime. Callers own DTOs, scope validation and policy. */
export function useActiveScopedRead<T>({ scopeKey, active, read, refreshAt }: {
  scopeKey: string; active: boolean; read: (signal: AbortSignal) => Promise<T>;
  refreshAt?: (value: T) => number | null;
}) {
  const { status, user, sessionRevision } = useAuth();
  const [revision, setRevision] = useState(0);
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState !== "hidden");
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  const [result, setResult] = useState<{ key: string; scope: ReturnType<typeof captureAuthRequestScope>; value: T } | null>(null);
  const [phase, setPhase] = useState<{ key: string; loading: boolean; error: boolean }>({ key: scopeKey, loading: true, error: false });
  const key = JSON.stringify([scopeKey, user?.id, sessionRevision, runtimeRevision]);
  useEffect(() => {
    const changed = () => { setResult(null); setRuntimeRevision(value => value + 1); };
    const visibility = () => { setVisible(document.visibilityState !== "hidden"); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    document.addEventListener("visibilitychange", visibility);
    return () => { window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  useEffect(() => {
    if (!active || !visible || status !== "authenticated") return;
    const controller = new AbortController(), scope = captureAuthRequestScope();
    const current = () => !controller.signal.aborted && document.visibilityState !== "hidden" && isCurrentAuthRequestScope(scope);
    queueMicrotask(() => { if (current()) setPhase({ key, loading: true, error: false }); });
    void read(controller.signal).then(value => {
      if (current()) { setResult({ key, scope, value }); setPhase({ key, loading: false, error: false }); }
    }).catch(error => {
      if (!current()) return;
      if (error && typeof error === "object" && "status" in error && [401, 403, 404].includes(Number(error.status))) setResult(null);
      setPhase({ key, loading: false, error: true });
    });
    return () => controller.abort();
  }, [active, visible, status, key, revision, read]);
  const data = status === "authenticated" && result?.key === key && isCurrentAuthRequestScope(result.scope) ? result.value : null;
  useEffect(() => {
    if (!active || !visible || !data || !refreshAt) return;
    const deadline = refreshAt(data);
    if (deadline === null) return;
    const timer = setTimeout(() => setRevision(value => value + 1), Math.max(1000, deadline - Date.now()));
    return () => clearTimeout(timer);
  }, [active, visible, data, refreshAt]);
  return { identity: key, data, loading: phase.key !== key || phase.loading, error: phase.key === key && phase.error, refresh: () => setRevision(value => value + 1) };
}
