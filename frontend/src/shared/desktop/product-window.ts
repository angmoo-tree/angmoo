export type AngmooDesktopWindowKind =
  | "phone"
  | "studio"
  | "relationship-graph";

export type AngmooDesktopWindowState = {
  kind: AngmooDesktopWindowKind;
  route: string;
};

type TauriInvoke = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>;

declare global {
  interface Window {
    __ANGMOO_DESKTOP_WINDOW__?: AngmooDesktopWindowState;
    __TAURI__?: {
      core?: {
        invoke?: TauriInvoke;
      };
    };
  }
}

export const DESKTOP_ROUTE_EVENT = "angmoo:desktop-route";

export function isTauriDesktopRuntime() {
  return (
    typeof window !== "undefined" &&
    typeof window.__TAURI__?.core?.invoke === "function"
  );
}

export function getDesktopWindowState(): AngmooDesktopWindowState | null {
  if (typeof window === "undefined" || !isTauriDesktopRuntime()) return null;
  return (
    window.__ANGMOO_DESKTOP_WINDOW__ ?? {
      kind: "phone",
      route: `${window.location.pathname}${window.location.search}`,
    }
  );
}

export function desktopWindowKindForRoute(
  route: string,
): AngmooDesktopWindowKind {
  const pathname = routePathname(route);
  if (pathname === "/studio" || pathname.startsWith("/studio/")) {
    return "studio";
  }
  if (
    /^\/characters\/[^/]+\/worlds\/[^/]+\/relationship-graph$/.test(
      pathname,
    )
  ) {
    return "relationship-graph";
  }
  return "phone";
}

export function currentDesktopRoute() {
  const state = getDesktopWindowState();
  if (state) return state.route;
  if (typeof window === "undefined") return "";
  return `${window.location.pathname}${window.location.search}`;
}

export function subscribeDesktopRoute(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(DESKTOP_ROUTE_EVENT, onStoreChange);
  window.addEventListener("popstate", onStoreChange);
  return () => {
    window.removeEventListener(DESKTOP_ROUTE_EVENT, onStoreChange);
    window.removeEventListener("popstate", onStoreChange);
  };
}

export function navigateCurrentDesktopRoute(route: string, replace = false) {
  if (!isTauriDesktopRuntime()) return false;
  const state = getDesktopWindowState();
  if (!state) return false;
  const normalized = normalizeInternalRoute(route);
  window.__ANGMOO_DESKTOP_WINDOW__ = { ...state, route: normalized };
  if (replace) window.history.replaceState(null, "", normalized);
  else window.history.pushState(null, "", normalized);
  window.dispatchEvent(new Event(DESKTOP_ROUTE_EVENT));
  return true;
}

export async function openDesktopProductWindow(
  kind: AngmooDesktopWindowKind,
  route: string,
) {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return false;
  await invoke("open_product_window", {
    kind,
    route: normalizeInternalRoute(route),
  });
  return true;
}

export async function invokeDesktopWindowCommand(
  command:
    | "close_product_window"
    | "minimize_product_window"
    | "start_product_window_drag",
) {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return false;
  await invoke(command);
  return true;
}

export function normalizeInternalRoute(route: string) {
  const parsed = new URL(route, "http://angmoo.local");
  if (parsed.origin !== "http://angmoo.local") {
    throw new Error("desktop_route_must_be_internal");
  }
  const pathname = parsed.pathname.replace(/\/+$/, "") || "/";
  return `${pathname}${parsed.search}${parsed.hash}`;
}

function routePathname(route: string) {
  return new URL(normalizeInternalRoute(route), "http://angmoo.local").pathname;
}
