"use client";

import { useEffect, useState } from "react";

import {
  DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
  getRuntimeConfig,
  resolveRuntimeMediaUrl,
  runtimeFetch,
} from "@/lib/runtime/runtime-config";
import { AUTH_CHANGED_EVENT, captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";

export function useRuntimeMediaUrl(sourceUrl: string | null | undefined) {
  const source = sourceUrl?.trim() ?? "";
  const resolvedSource = source ? resolveRuntimeMediaUrl(source) : "";
  const runtime = getRuntimeConfig();
  const requiresAuthenticatedFetch = Boolean(
    source.startsWith("/api/v1/media/assets/") || source.startsWith("/media/worlds/") || (runtime?.launchToken &&
      (resolvedSource === `${runtime.apiBaseUrl}/media` ||
        resolvedSource.startsWith(`${runtime.apiBaseUrl}/media/`))),
  );
  const [scopeRevision, setScopeRevision] = useState(0);
  const [objectUrl, setObjectUrl] = useState<{
    source: string;
    scopeRevision: number;
    value: string;
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
    if (!requiresAuthenticatedFetch || !resolvedSource) return;
    let active = true;
    let createdUrl: string | null = null;
    const scope = captureAuthRequestScope();
    runtimeFetch(resolvedSource, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`media_http_${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        createdUrl = URL.createObjectURL(blob);
        if (active && isCurrentAuthRequestScope(scope)) {
          setObjectUrl({ source: resolvedSource, scopeRevision, value: createdUrl });
        } else {
          URL.revokeObjectURL(createdUrl);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [requiresAuthenticatedFetch, resolvedSource, scopeRevision]);

  if (!resolvedSource) return null;
  if (!requiresAuthenticatedFetch) return resolvedSource;
  return objectUrl?.source === resolvedSource && objectUrl.scopeRevision === scopeRevision ? objectUrl.value : null;
}
