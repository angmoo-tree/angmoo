import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ApiRequestError } from "@/lib/http/error-contract";
import { getWorldNotificationCount, getWorldNotifications, markAllWorldNotificationsRead, notificationSnapshotRejected } from "../api/world-notifications";
import type { NotificationScope, WorldNotification, WorldNotificationPage } from "../types/world-notifications";

export const NOTIFICATION_REFRESH_MS = 60_000;
export const NOTIFICATION_READ_TIMEOUT_MS = 15_000;
const JOURNAL_KEY = "angmoo.notifications.read-attempts";
export type NotificationMode = "feed" | "list" | null;
export type NotificationState = {
  scope: NotificationScope | null; unreadCount: number | null; items: WorldNotification[];
  nextCursor: string | null; loading: boolean; loadingMore: boolean; error: boolean;
  stale: boolean; readAllPending: boolean; readAllStatus: "idle" | "success" | "failed" | "uncertain";
};
export const EMPTY_NOTIFICATION_STATE: NotificationState = { scope: null, unreadCount: null, items: [], nextCursor: null,
  loading: false, loadingMore: false, error: false, stale: false, readAllPending: false, readAllStatus: "idle" };
export function sameNotificationScope(a: NotificationScope | null, b: NotificationScope | null) {
  return !!a && !!b && a.world_id === b.world_id && a.recipient_world_character_id === b.recipient_world_character_id;
}

/** One selected World and one explicit bulk command; reads never mutate on entry. */
export function createWorldNotificationController(userId: string, sessionRevision: number) {
  let state = EMPTY_NOTIFICATION_STATE;
  const listeners = new Set<() => void>();
  let mode: NotificationMode = null, generation = 0, mutationEpoch = 0, disposed = false, owners = 0;
  let query: AbortController | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let lastResume = -Infinity;
  let mutation: AbortController | null = null;
  const admission = captureAuthRequestScope();
  const current = () => !disposed && isCurrentAuthRequestScope(admission);
  const emit = (patch: Partial<NotificationState>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
  const journal = () => {
    try {
      if (state.scope && (state.readAllPending || state.readAllStatus === "failed" || state.readAllStatus === "uncertain"))
        sessionStorage.setItem(JOURNAL_KEY, JSON.stringify({ version: 2, userId, sessionRevision, scope: state.scope, unconfirmed: true }));
      else sessionStorage.removeItem(JOURNAL_KEY);
    } catch { /* The live controller remains authoritative if storage is unavailable. */ }
  };
  const cancelQuery = () => { generation++; query?.abort(); query = null; };
  const stopTimer = () => { if (timer) clearInterval(timer); timer = null; };
  const refresh = async (append = false) => {
    if (!current() || !state.scope || !mode || document.visibilityState === "hidden" || query) return;
    const scope = state.scope, requestMode = mode, sequence = ++generation;
    const request = new AbortController(); query = request;
    emit({ loading: !append && state.unreadCount === null, loadingMore: append, error: false });
    try {
      const page = requestMode === "list" ? await getWorldNotifications(scope, request.signal, append ? state.nextCursor : null)
        : await getWorldNotificationCount(scope, request.signal);
      if (!current() || sequence !== generation || !sameNotificationScope(scope, state.scope)) return;
      const list = "items" in page ? page as WorldNotificationPage : null;
      emit({ unreadCount: page.unread_count, loading: false, loadingMore: false, error: false, stale: false,
        ...(!state.readAllPending && page.unread_count === 0 && ["failed", "uncertain"].includes(state.readAllStatus) ? { readAllStatus: "idle" as const } : {}),
        ...(list ? { items: append ? [...state.items, ...list.items.filter(item => !state.items.some(old => old.id === item.id))] : list.items, nextCursor: list.next_cursor } : {}) });
      journal();
    } catch (error) {
      if (current() && sequence === generation && notificationSnapshotRejected(error)) mutationEpoch++;
      if (current() && sequence === generation) emit({ loading: false, loadingMore: false, error: true,
        stale: !notificationSnapshotRejected(error) && state.unreadCount !== null,
        ...(notificationSnapshotRejected(error) ? { unreadCount: null, items: [], nextCursor: null, readAllStatus: "idle" } : {}) });
    } finally { if (query === request) query = null; }
  };
  const resume = () => {
    stopTimer();
    if (!mode || document.visibilityState === "hidden" || !current()) { cancelQuery(); return; }
    const now = performance.now();
    if (now - lastResume > 250) { lastResume = now; void refresh(); }
    timer = setInterval(() => { void refresh(); }, NOTIFICATION_REFRESH_MS);
  };
  const markAllRead = async () => {
    if (!current() || !state.scope || mutation || state.unreadCount === null || state.unreadCount === 0) return;
    const scope = state.scope, request = new AbortController(), epoch = ++mutationEpoch;
    mutation = request; cancelQuery();
    const timeout = setTimeout(() => request.abort(), NOTIFICATION_READ_TIMEOUT_MS);
    emit({ readAllPending: true, readAllStatus: "idle", loading: false, loadingMore: false });
    journal();
    try {
      const result = await markAllWorldNotificationsRead(scope, request.signal);
      if (!current() || !sameNotificationScope(scope, state.scope) || epoch !== mutationEpoch) return;
      cancelQuery();
      emit({ unreadCount: result.unread_count, items: state.items.map(item => !item.read_at && result.read_at &&
        result.through_notification_id !== null && item.id <= result.through_notification_id ? { ...item, read_at: result.read_at } : item),
        readAllStatus: "success", stale: false });
    } catch (error) {
      if (!current() || !sameNotificationScope(scope, state.scope) || epoch !== mutationEpoch) return;
      const rejected = notificationSnapshotRejected(error);
      const failed = error instanceof ApiRequestError && (error.status >= 400 && error.status < 500 || error.code === "sqlite_busy_retry_exhausted");
      if (rejected) mutationEpoch++;
      emit({ readAllStatus: rejected ? "idle" : failed ? "failed" : "uncertain",
        ...(rejected ? { unreadCount: null, items: [], nextCursor: null, error: true, stale: false } : {}) });
    } finally {
      clearTimeout(timeout);
      if (mutation === request) {
        mutation = null;
        if (current() && sameNotificationScope(scope, state.scope)) {
          emit({ readAllPending: false }); journal();
          // The command may have committed despite a lost response. Reconcile
          // with one GET, never automatically replay an all-current-unread write.
          void refresh();
        }
      }
    }
  };
  const onReturn = () => { if (document.visibilityState !== "hidden") resume(); else { stopTimer(); cancelQuery(); } };
  const dispose = () => {
    disposed = true; stopTimer(); cancelQuery(); mutation?.abort(); mutation = null;
    listeners.clear(); window.removeEventListener("focus", onReturn); document.removeEventListener("visibilitychange", onReturn);
  };
  return {
    connect() {
      owners++;
      let released = false;
      return () => {
        if (released) return;
        released = true; owners--;
        // React's development setup/cleanup/setup retains the same memoized
        // controller. Dispose only if no owner reconnects in that cycle.
        queueMicrotask(() => { if (!owners) dispose(); });
      };
    },
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn); }; },
    getSnapshot: () => state,
    activate(scope: NotificationScope, nextMode: NotificationMode) {
      if (!sameNotificationScope(scope, state.scope)) {
        cancelQuery(); mutationEpoch++; mutation?.abort(); mutation = null;
        let unconfirmed = false;
        try {
          const saved = JSON.parse(sessionStorage.getItem(JOURNAL_KEY) ?? "null");
          unconfirmed = saved?.version === 2 && saved.userId === userId && saved.sessionRevision === sessionRevision && sameNotificationScope(saved.scope, scope) && saved.unconfirmed === true;
        } catch { /* No persisted command outcome is assumed. */ }
        emit({ ...EMPTY_NOTIFICATION_STATE, scope, readAllStatus: unconfirmed ? "uncertain" : "idle" }); journal();
      } else cancelQuery();
      mode = nextMode;
      lastResume = -Infinity;
      window.addEventListener("focus", onReturn); document.addEventListener("visibilitychange", onReturn);
      resume();
    },
    deactivate() { mode = null; stopTimer(); cancelQuery(); window.removeEventListener("focus", onReturn); document.removeEventListener("visibilitychange", onReturn); },
    refresh() { cancelQuery(); return refresh(); },
    loadMore() { return state.nextCursor && !state.loadingMore ? refresh(true) : Promise.resolve(); },
    markAllRead,
    dispose,
  };
}
export type WorldNotificationController = ReturnType<typeof createWorldNotificationController>;
