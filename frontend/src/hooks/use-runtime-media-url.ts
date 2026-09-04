"use client";

import { useEffect, useState } from "react";

import {
  getRuntimeConfig,
  resolveRuntimeMediaUrl,
  runtimeFetch,
} from "@/lib/runtime/runtime-config";

export function useRuntimeMediaUrl(sourceUrl: string | null | undefined) {
  const source = sourceUrl?.trim() ?? "";
  const resolvedSource = source ? resolveRuntimeMediaUrl(source) : "";
  const runtime = getRuntimeConfig();
  const requiresAuthenticatedFetch = Boolean(
    runtime?.launchToken &&
      (resolvedSource === `${runtime.apiBaseUrl}/media` ||
        resolvedSource.startsWith(`${runtime.apiBaseUrl}/media/`)),
  );
  const [objectUrl, setObjectUrl] = useState<{
    source: string;
    value: string;
  } | null>(null);

  useEffect(() => {
    if (!requiresAuthenticatedFetch || !resolvedSource) return;
    let active = true;
    let createdUrl: string | null = null;
    runtimeFetch(resolvedSource, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`media_http_${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        createdUrl = URL.createObjectURL(blob);
        if (active) {
          setObjectUrl({ source: resolvedSource, value: createdUrl });
        } else {
          URL.revokeObjectURL(createdUrl);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [requiresAuthenticatedFetch, resolvedSource]);

  if (!resolvedSource) return null;
  if (!requiresAuthenticatedFetch) return resolvedSource;
  return objectUrl?.source === resolvedSource ? objectUrl.value : null;
}
