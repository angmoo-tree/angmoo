"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { getWorldUnreadCounts, notificationSnapshotRejected } from "../api/world-notifications";
import type { WorldUnreadCount } from "../types/world-notifications";
import { NOTIFICATION_REFRESH_MS } from "./world-notification-controller";

/** One read-only batch for the visible home set; no identity/list initialization. */
export function useWorldUnreadCounts(worldIds: string[]) {
  const { user, status, sessionRevision } = useAuth();
  const idsKey = JSON.stringify([...new Set(worldIds)].sort());
  const key = `${status}:${user?.id ?? ""}:${sessionRevision}:${idsKey}`;
  const [state, setState] = useState<{ key: string; records: Record<string, WorldUnreadCount>; error: boolean; stale: boolean }>({ key: "", records: {}, error: false, stale: false });
  useEffect(() => {
    const ids = JSON.parse(idsKey) as string[];
    if (status !== "authenticated" || !ids.length) return;
    const admission = captureAuthRequestScope();
    let alive = true, request: AbortController | null = null, generation = 0;
    let timer: ReturnType<typeof setInterval> | null = null;
    let lastResume = -Infinity;
    const cancel = () => { generation++; request?.abort(); request = null; };
    const stop = () => { if (timer) clearInterval(timer); timer = null; };
    const refresh = async () => {
      if (!alive || !isCurrentAuthRequestScope(admission) || request || document.visibilityState === "hidden") return;
      const controller = new AbortController(), sequence = ++generation;
      request = controller;
      try {
        const items = await getWorldUnreadCounts(ids, controller.signal);
        if (alive && isCurrentAuthRequestScope(admission) && sequence === generation) setState({ key, records: Object.fromEntries(items.map(item => [item.world_id, item])), error: false, stale: false });
      } catch (error) {
        if (alive && isCurrentAuthRequestScope(admission) && sequence === generation) setState(previous => ({ key,
          records: previous.key === key && !notificationSnapshotRejected(error) ? previous.records : {}, error: true,
          stale: !notificationSnapshotRejected(error) && previous.key === key && Object.keys(previous.records).length > 0 }));
      } finally { if (request === controller) request = null; }
    };
    const resume = () => {
      stop();
      if (document.visibilityState === "hidden") { cancel(); return; }
      // Browsers commonly send focus and visibilitychange for one return.
      const now = performance.now();
      if (now - lastResume > 250) { lastResume = now; void refresh(); }
      timer = setInterval(() => { void refresh(); }, NOTIFICATION_REFRESH_MS);
    };
    resume();
    window.addEventListener("focus", resume); document.addEventListener("visibilitychange", resume);
    return () => { alive = false; stop(); cancel(); window.removeEventListener("focus", resume); document.removeEventListener("visibilitychange", resume); };
  }, [key, idsKey, status]);
  return state.key === key ? state : { key, records: {} as Record<string, WorldUnreadCount>, error: false, stale: false };
}
