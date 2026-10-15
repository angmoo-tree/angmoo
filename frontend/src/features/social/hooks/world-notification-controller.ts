import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { getWorldNotificationCount, getWorldNotifications, readWorldNotification, notificationSnapshotRejected } from "../api/world-notifications";
import type { NotificationScope, WorldNotification, WorldNotificationPage } from "../types/world-notifications";

export const NOTIFICATION_REFRESH_MS = 60_000;
const JOURNAL_KEY = "angmoo.notifications.read-attempts";
export type NotificationMode = "feed" | "list" | null;
export type NotificationState = {
  scope: NotificationScope | null; unreadCount: number | null; items: WorldNotification[];
  nextCursor: string | null; loading: boolean; loadingMore: boolean; error: boolean;
  stale: boolean; reading: ReadonlySet<number>; readErrors: ReadonlySet<number>;
};
export const EMPTY_NOTIFICATION_STATE: NotificationState = { scope: null, unreadCount: null, items: [], nextCursor: null,
  loading: false, loadingMore: false, error: false, stale: false, reading: new Set(), readErrors: new Set() };
export function sameNotificationScope(a: NotificationScope | null, b: NotificationScope | null) {
  return !!a && !!b && a.world_id === b.world_id && a.recipient_world_character_id === b.recipient_world_character_id;
}

/** One currently selected World, one query timer; explicit reads outlive views. */
export function createWorldNotificationController(userId: string, sessionRevision: number) {
  let state = EMPTY_NOTIFICATION_STATE;
  const listeners = new Set<() => void>();
  let mode: NotificationMode = null, generation = 0, mutationEpoch = 0, disposed = false;
  let query: AbortController | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let lastResume = -Infinity;
  const mutations = new Map<number, AbortController>();
  const admission = captureAuthRequestScope();
  const current = () => !disposed && isCurrentAuthRequestScope(admission);
  const emit = (patch: Partial<NotificationState>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
  const journal = () => {
    try {
      const ids = [...new Set([...state.reading, ...state.readErrors])];
      if (state.scope && ids.length) sessionStorage.setItem(JOURNAL_KEY, JSON.stringify({ userId, sessionRevision, scope: state.scope, ids }));
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
      const readErrors = new Set(state.readErrors);
      list?.items.forEach(item => { if (item.read_at) readErrors.delete(item.id); });
      emit({ unreadCount: page.unread_count, loading: false, loadingMore: false, error: false, stale: false, readErrors,
        ...(list ? { items: append ? [...state.items, ...list.items.filter(item => !state.items.some(old => old.id === item.id))] : list.items, nextCursor: list.next_cursor } : {}) });
      journal();
    } catch (error) {
      if (current() && sequence === generation && notificationSnapshotRejected(error)) mutationEpoch++;
      if (current() && sequence === generation) emit({ loading: false, loadingMore: false, error: true,
        stale: !notificationSnapshotRejected(error) && state.unreadCount !== null,
        ...(notificationSnapshotRejected(error) ? { unreadCount: null, items: [], nextCursor: null } : {}) });
    } finally { if (query === request) query = null; }
  };
  const resume = () => {
    stopTimer();
    if (!mode || document.visibilityState === "hidden" || !current()) { cancelQuery(); return; }
    const now = performance.now();
    if (now - lastResume > 250) { lastResume = now; void refresh(); }
    timer = setInterval(() => { void refresh(); }, NOTIFICATION_REFRESH_MS);
  };
  const read = async (id: number) => {
    const item = state.items.find(item => item.id === id);
    if (!current() || !state.scope || !item || mutations.has(id) || item.read_at) return;
    const scope = state.scope, request = new AbortController(), epoch = ++mutationEpoch;
    mutations.set(id, request); cancelQuery();
    emit({ reading: new Set([...state.reading, id]), readErrors: new Set([...state.readErrors].filter(value => value !== id)), loading: false, loadingMore: false });
    journal();
    try {
      const result = await readWorldNotification(scope, id, request.signal);
      if (!current() || !sameNotificationScope(scope, state.scope)) return;
      cancelQuery();
      emit({ ...(epoch === mutationEpoch ? { unreadCount: result.unread_count } : {}), items: state.items.map(item => item.id === id ? { ...item, read_at: result.read_at } : item),
        readErrors: new Set([...state.readErrors].filter(value => value !== id)), stale: false });
    } catch (error) {
      if (current() && sameNotificationScope(scope, state.scope) && notificationSnapshotRejected(error)) mutationEpoch++;
      if (current() && sameNotificationScope(scope, state.scope)) emit({ readErrors: new Set([...state.readErrors, id]),
        ...(notificationSnapshotRejected(error) ? { unreadCount: null, items: [], nextCursor: null, error: true, stale: false } : {}) });
    } finally {
      if (mutations.get(id) === request) mutations.delete(id);
      if (current() && sameNotificationScope(scope, state.scope)) {
        emit({ reading: new Set([...state.reading].filter(value => value !== id)) }); journal();
        // A response may have been lost after the server committed the read.
        if (!mutations.size) void refresh();
      }
    }
  };
  const onReturn = () => { if (document.visibilityState !== "hidden") resume(); else { stopTimer(); cancelQuery(); } };
  return {
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn); }; },
    getSnapshot: () => state,
    activate(scope: NotificationScope, nextMode: NotificationMode) {
      if (!sameNotificationScope(scope, state.scope)) {
        cancelQuery(); mutations.forEach(value => value.abort()); mutations.clear();
        let failed: number[] = [];
        try {
          const saved = JSON.parse(sessionStorage.getItem(JOURNAL_KEY) ?? "null");
          if (saved?.userId === userId && saved.sessionRevision === sessionRevision && sameNotificationScope(saved.scope, scope) && Array.isArray(saved.ids)) failed = saved.ids.filter((id: unknown) => Number.isSafeInteger(id) && Number(id) > 0);
        } catch { /* No persisted command outcome is assumed. */ }
        emit({ ...EMPTY_NOTIFICATION_STATE, scope, readErrors: new Set(failed) }); journal();
      } else cancelQuery();
      mode = nextMode;
      lastResume = -Infinity;
      window.addEventListener("focus", onReturn); document.addEventListener("visibilitychange", onReturn);
      resume();
    },
    deactivate() { mode = null; stopTimer(); cancelQuery(); window.removeEventListener("focus", onReturn); document.removeEventListener("visibilitychange", onReturn); },
    refresh() { cancelQuery(); return refresh(); },
    loadMore() { return state.nextCursor && !state.loadingMore ? refresh(true) : Promise.resolve(); },
    read,
    dispose() { disposed = true; stopTimer(); cancelQuery(); mutations.forEach(value => value.abort()); mutations.clear(); listeners.clear(); window.removeEventListener("focus", onReturn); document.removeEventListener("visibilitychange", onReturn); },
  };
}
export type WorldNotificationController = ReturnType<typeof createWorldNotificationController>;
