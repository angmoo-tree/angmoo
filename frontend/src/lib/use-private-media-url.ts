"use client";

import { useEffect, useState } from "react";

import { fetchAuthenticatedMediaObjectUrl } from "@/lib/agents";


export function usePrivateMediaUrl(sourceUrl: string | null | undefined) {
  const source = sourceUrl?.trim() ?? "";
  const isPrivate = source.startsWith("/api/v1/agents/");
  const [resolved, setResolved] = useState<{
    source: string;
    url: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    if (!isPrivate) return;
    fetchAuthenticatedMediaObjectUrl(source)
      .then((url) => {
        objectUrl = url;
        if (active) setResolved({ source, url });
        else URL.revokeObjectURL(url);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [isPrivate, source]);

  if (!source) return null;
  if (!isPrivate) return source;
  return resolved?.source === source ? resolved.url : null;
}
