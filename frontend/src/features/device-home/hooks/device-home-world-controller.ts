import type { WorldSurfaceItem } from "@/features/device-home/types/index";

export type HomeWorldSnapshot = {
  items: WorldSurfaceItem[];
  hasSnapshot: boolean;
  loading: boolean;
  error: "unavailable" | "denied" | null;
};
type Ports = {
  ensure: () => Promise<unknown>;
  read: (signal: AbortSignal) => Promise<{ items: WorldSurfaceItem[] }>;
  captureScope: () => () => boolean;
  transient: (error: unknown) => boolean;
  now?: () => number;
};

/** One Home lifetime owns preparation and reads. No global cache or polling. */
export function createDeviceHomeWorldController(ports: Ports) {
  let snapshot: HomeWorldSnapshot = { items: [], hasSnapshot: false, loading: true, error: null };
  const listeners = new Set<() => void>();
  const now = ports.now ?? (() => performance.now());
  let active = false, visible = true, prepared = false, allowed = false;
  let currentScope: (() => boolean) | undefined;
  let preparation: Promise<void> | undefined;
  let request: AbortController | undefined;
  let pending = false, generation = 0, lastStarted = -Infinity;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const publish = (next: HomeWorldSnapshot) => { snapshot = next; listeners.forEach(listener => listener()); };
  const valid = () => active && visible && currentScope?.();
  const cancel = () => { generation++; request?.abort(); pending = false; lastStarted = -Infinity; if (timer !== undefined) clearTimeout(timer); timer = undefined; };
  const refresh = async (reason: "resume" | "retry" | "initial" = "resume") => {
    if (!active || !visible || (!allowed && !prepared)) return;
    currentScope ??= ports.captureScope();
    if (!currentScope()) { cancel(); publish({ items: [], hasSnapshot: false, loading: false, error: "denied" }); return; }
    // focus and visibilitychange describe the same return. A later event
    // during a slow request may request one (and only one) follow-up read.
    if (reason === "resume" && now() - lastStarted < 250) return;
    if (request) { if (reason !== "retry") pending = true; return; }
    lastStarted = now();
    const controller = new AbortController(); request = controller;
    const revision = ++generation;
    publish({ ...snapshot, loading: true });
    try {
      if (!prepared) {
        preparation ??= Promise.resolve().then(ports.ensure).then(() => {
          if (!currentScope?.()) throw new DOMException("Scope changed", "AbortError");
          prepared = true;
        }).finally(() => { preparation = undefined; });
        await preparation;
      }
      if (!valid() || controller.signal.aborted || revision !== generation) return;
      const result = await ports.read(controller.signal);
      if (!valid() || controller.signal.aborted || revision !== generation) return;
      publish({ items: result.items, hasSnapshot: true, loading: false, error: null });
    } catch (error) {
      if (!valid() || controller.signal.aborted || revision !== generation) return;
      const retain = snapshot.hasSnapshot && ports.transient(error);
      publish({ items: retain ? snapshot.items : [], hasSnapshot: retain, loading: false,
        error: ports.transient(error) ? "unavailable" : "denied" });
    } finally {
      if (request === controller) request = undefined;
      if (pending && valid()) {
        pending = false;
        timer = setTimeout(() => { timer = undefined; void refresh("initial"); }, Math.max(0, 250 - (now() - lastStarted)));
      }
    }
  };
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    activate: (ready: boolean, isVisible: boolean) => { active = true; allowed = ready; visible = isVisible; void refresh("initial"); },
    deactivate: () => { active = false; cancel(); },
    visibility: (isVisible: boolean) => { visible = isVisible; if (!visible) cancel(); else void refresh(); },
    resume: () => { void refresh(); },
    retry: () => { void refresh("retry"); },
  };
}
