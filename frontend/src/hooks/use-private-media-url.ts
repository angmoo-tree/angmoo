"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchAuthenticatedMediaObjectUrl } from "@/lib/media/authenticated-media";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { useAuthRuntimeIdentity } from "./use-auth-runtime-identity";


/** Retain the last good preview during an explicit refresh of the same resource. */
export function usePrivateMediaResource(sourceUrl: string | null | undefined, revision = 0) {
  const source = sourceUrl?.trim() ?? "";
  const scope = useAuthRuntimeIdentity(source);
  const isPrivate = source.startsWith("/api/v1/agents/") || source.startsWith("/media/worlds/");
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(value => value + 1), []);
  const request = JSON.stringify([scope, revision, attempt]);
  const [resolved, setResolved] = useState<{ scope: string; url: string } | null>(null);
  const [result, setResult] = useState<{ request: string; error: boolean } | null>(null);
  const owned = useRef(new Set<string>());
  useEffect(() => {
    const urls = owned.current;
    return () => { for (const url of urls) URL.revokeObjectURL(url); urls.clear(); };
  }, [scope]);
  useEffect(() => {
    // Revoke a replaced preview after React has committed the new URL.
    for (const url of owned.current) if (url !== resolved?.url) { URL.revokeObjectURL(url); owned.current.delete(url); }
  }, [resolved]);
  useEffect(() => {
    if (!isPrivate) return;
    const controller = new AbortController();
    const auth = captureAuthRequestScope();
    const current = () => !controller.signal.aborted && isCurrentAuthRequestScope(auth);
    fetchAuthenticatedMediaObjectUrl(source, controller.signal).then(url => {
      if (!current()) { URL.revokeObjectURL(url); return; }
      owned.current.add(url);
      setResolved({ scope, url });
      setResult({ request, error: false });
    }).catch(() => { if (current()) setResult({ request, error: true }); });
    return () => controller.abort();
  }, [source, isPrivate, scope, request]);
  const current = result?.request === request ? result : null;
  return {
    url: !source ? null : !isPrivate ? source : resolved?.scope === scope ? resolved.url : null,
    loading: Boolean(source) && isPrivate && !current,
    error: Boolean(current?.error),
    retry,
  };
}

export function usePrivateMediaUrl(sourceUrl: string | null | undefined) {
  return usePrivateMediaResource(sourceUrl).url;
}
