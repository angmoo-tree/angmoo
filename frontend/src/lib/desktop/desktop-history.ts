const ENTRY_KEY = "__angmooProductHistory";
const SESSION_KEY = "angmoo.product-history.v1";
type Entry = { session: string; index: number };
type Session = { session: string; tail: number };

function entry(): Entry | null {
  const value = window.history.state?.[ENTRY_KEY] as Entry | undefined;
  return value && typeof value.session === "string" && Number.isSafeInteger(value.index) && value.index >= 0 ? value : null;
}
function session(): Session | null {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(SESSION_KEY) ?? "null") as Session | null;
    return value && typeof value.session === "string" && Number.isSafeInteger(value.tail) && value.tail >= 0 ? value : null;
  } catch { return null; }
}
function storeSession(value: Session) {
  try { window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(value)); return true; }
  catch { return false; }
}
export function desktopHistoryAvailability() {
  if (typeof window === "undefined") return { back: false, forward: false };
  const current = entry(), stored = session();
  if (!current || !stored || current.session !== stored.session || current.index > stored.tail) return { back: false, forward: false };
  return { back: current.index > 0, forward: current.index < stored.tail };
}

/** Add only indices/session metadata to real entries; never keep a route array. */
export function installDesktopHistory(onCommit: () => void) {
  const originalPush = window.history.pushState;
  const originalReplace = window.history.replaceState;
  let canInitialize = false;
  try { canInitialize = !Object.hasOwn(window.history.state ?? {}, ENTRY_KEY) && !window.sessionStorage.getItem(SESSION_KEY); } catch { /* Unknown history stays disabled. */ }
  if (canInitialize) {
    const initial = { session: crypto.randomUUID(), index: 0 };
    if (storeSession({ session: initial.session, tail: 0 })) {
      originalReplace.call(window.history, { ...window.history.state, [ENTRY_KEY]: initial }, "");
    }
  }
  const commit = (method: typeof originalPush, push: boolean, state: unknown, unused: string, url?: string | URL | null) => {
    const current = entry(), stored = session();
    let metadata: Entry | null = null;
    if (current && stored && current.session === stored.session && current.index <= stored.tail) {
      metadata = { session: current.session, index: current.index + (push ? 1 : 0) };
    }
    const next = { ...(state && typeof state === "object" ? state : {}), [ENTRY_KEY]: metadata };
    method.call(window.history, next, unused, url);
    // A rejected push (bad URL, cloning error, browser limit) must not discard
    // the real forward entries. Commit the tail only after the browser accepts.
    if (push && metadata && !storeSession({ session: metadata.session, tail: metadata.index })) {
      originalReplace.call(window.history, { ...window.history.state, [ENTRY_KEY]: null }, "");
    }
    queueMicrotask(onCommit);
  };
  const push: typeof originalPush = (state, unused, url) => commit(originalPush, true, state, unused, url);
  const replace: typeof originalReplace = (state, unused, url) => commit(originalReplace, false, state, unused, url);
  window.history.pushState = push;
  window.history.replaceState = replace;
  window.addEventListener("popstate", onCommit);
  onCommit();
  return () => {
    if (window.history.pushState === push) window.history.pushState = originalPush;
    if (window.history.replaceState === replace) window.history.replaceState = originalReplace;
    window.removeEventListener("popstate", onCommit);
  };
}
