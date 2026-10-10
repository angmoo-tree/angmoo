"use client";

import { useEffect, useState } from "react";
import { useAuth } from "./use-auth";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";

/** Component lifetime only; callers retain their authorization and DTO policy. */
export function useAuthRuntimeIdentity(scopeKey: string) {
  const { user, sessionRevision } = useAuth();
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  useEffect(() => {
    const changed = () => setRuntimeRevision(value => value + 1);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
  }, []);
  return JSON.stringify([scopeKey, user?.id ?? null, sessionRevision, runtimeRevision]);
}
