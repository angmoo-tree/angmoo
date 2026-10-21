"use client";

import { useCallback, useEffect, useState } from "react";

import {
  DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
  getRuntimeConfig,
  resolveRuntimeMediaUrl,
  runtimeFetch,
} from "@/lib/runtime/runtime-config";
import { AUTH_CHANGED_EVENT, captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";

export function useRuntimeMediaResource(sourceUrl: string | null | undefined, enabled = true) {
  const source = sourceUrl?.trim() ?? "";
  const resolvedSource = source ? resolveRuntimeMediaUrl(source) : "";
  const runtime = getRuntimeConfig();
  const requiresAuthenticatedFetch = Boolean(
    source.startsWith("/api/v1/media/assets/") || source.startsWith("/media/worlds/") || (runtime?.launchToken &&
      (resolvedSource === `${runtime.apiBaseUrl}/media` ||
        resolvedSource.startsWith(`${runtime.apiBaseUrl}/media/`))),
  );
  const [scopeRevision, setScopeRevision] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(value => value + 1), []);
  const [objectUrl, setObjectUrl] = useState<{
    source: string;
    scopeRevision: number;
    value: string | null;
    failed: boolean;
    attempt: number;
  } | null>(null);

  useEffect(() => {
    const changed = () => setScopeRevision(value => value + 1);
    window.addEventListener(AUTH_CHANGED_EVENT, changed);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, changed);
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    };
  }, []);

  useEffect(() => {
    if (!enabled || !requiresAuthenticatedFetch || !resolvedSource) return;
    const controller = new AbortController();
    let active = true;
    let createdUrl: string | null = null;
    const scope = captureAuthRequestScope();
    runtimeFetch(resolvedSource, { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`media_http_${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        createdUrl = URL.createObjectURL(blob);
        if (active && isCurrentAuthRequestScope(scope)) {
          setObjectUrl({ source: resolvedSource, scopeRevision, value: createdUrl, failed: false, attempt });
        } else {
          URL.revokeObjectURL(createdUrl);
        }
      })
      .catch(() => { if (active && !controller.signal.aborted && isCurrentAuthRequestScope(scope)) setObjectUrl({ source: resolvedSource, scopeRevision, value: null, failed: true, attempt }); });
    return () => {
      active = false; controller.abort();
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [requiresAuthenticatedFetch, resolvedSource, scopeRevision, enabled, attempt]);

  const current = objectUrl?.source === resolvedSource && objectUrl.scopeRevision === scopeRevision && objectUrl.attempt === attempt ? objectUrl : null;
  const url = !enabled || !resolvedSource ? null : !requiresAuthenticatedFetch ? resolvedSource : current?.value ?? null;
  return { url, retry, attempt, error: enabled && Boolean(current?.failed), loading: enabled && Boolean(resolvedSource) && !url && !current?.failed };
}

export function useRuntimeMediaUrl(sourceUrl: string | null | undefined) {
  return useRuntimeMediaResource(sourceUrl).url;
}
