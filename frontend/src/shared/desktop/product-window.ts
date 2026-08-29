export type AngmooDesktopWindowKind =
  | "phone"
  | "studio"
  | "relationship-graph";

export type AngmooDesktopWindowState = {
  kind: AngmooDesktopWindowKind;
  route: string;
};

export type AngmooPhoneResizeDirection =
  | "east"
  | "north"
  | "north-east"
  | "north-west"
  | "south"
  | "south-east"
  | "south-west"
  | "west";

export type AngmooDesktopRuntimeStatus = {
  phase: "starting" | "ready" | "crashed" | "stopped";
  runtimeMode?: "installed-sidecar" | "contributor-docker-bridge";
  apiBaseUrl?: string;
  graphProvider?: "ladybug";
  launchToken?: string;
  diagnosticCode?: string;
};

export type DesktopProductNavigationResult =
  | { handled: false; mode: "browser" }
  | { handled: true; mode: "same-window" }
  | { handled: true; mode: "cross-window" };

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
const DESKTOP_WINDOW_KIND_QUERY = "__angmoo_window_kind";
const DESKTOP_WINDOW_ROUTE_QUERY = "__angmoo_window_route";
const DESKTOP_WINDOW_KINDS = new Set<AngmooDesktopWindowKind>([
  "phone",
  "studio",
  "relationship-graph",
]);

export function isTauriDesktopRuntime() {
  return (
    typeof window !== "undefined" &&
    typeof window.__TAURI__?.core?.invoke === "function"
  );
}

export function getDesktopWindowState(): AngmooDesktopWindowState | null {
  if (typeof window === "undefined") return null;
  if (window.__ANGMOO_DESKTOP_WINDOW__) {
    return {
      ...window.__ANGMOO_DESKTOP_WINDOW__,
      route: canonicalProductRoute(window.__ANGMOO_DESKTOP_WINDOW__.route),
    };
  }
  const bootstrap = desktopWindowStateFromBootstrapQuery();
  if (bootstrap) return bootstrap;
  if (!isTauriDesktopRuntime()) return null;
  return {
    kind: "phone",
    route: normalizeInternalRoute(
      `${window.location.pathname}${window.location.search}`,
    ),
  };
}

function desktopWindowStateFromBootstrapQuery(): AngmooDesktopWindowState | null {
  const params = new URLSearchParams(window.location.search);
  const rawKind = params.get(DESKTOP_WINDOW_KIND_QUERY);
  // `main` was the Tauri window label used by early ER6 installers. Window
  // labels are host details; recover those candidates as the logical Phone.
  const kind = rawKind === "main" ? "phone" : rawKind;
  const route = params.get(DESKTOP_WINDOW_ROUTE_QUERY);
  if (!kind || !DESKTOP_WINDOW_KINDS.has(kind as AngmooDesktopWindowKind) || !route) {
    return null;
  }
  try {
    return {
      kind: kind as AngmooDesktopWindowKind,
      route: canonicalProductRoute(route),
    };
  } catch {
    return null;
  }
}

export function consumeDesktopWindowBootstrapRoute(
  state: AngmooDesktopWindowState,
) {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  if (
    !params.has(DESKTOP_WINDOW_KIND_QUERY) &&
    !params.has(DESKTOP_WINDOW_ROUTE_QUERY)
  ) {
    return;
  }
  window.history.replaceState(null, "", state.route);
}

export function desktopWindowKindForRoute(
  route: string,
): AngmooDesktopWindowKind {
  const pathname = routePathname(canonicalProductRoute(route));
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
  const normalized = canonicalProductRoute(route);
  if (desktopWindowKindForRoute(normalized) !== state.kind) return false;
  window.__ANGMOO_DESKTOP_WINDOW__ = { ...state, route: normalized };
  if (replace) window.history.replaceState(null, "", normalized);
  else window.history.pushState(null, "", normalized);
  window.dispatchEvent(new Event(DESKTOP_ROUTE_EVENT));
  return true;
}

export async function navigateDesktopProductRoute(
  route: string,
  replace = false,
): Promise<DesktopProductNavigationResult> {
  if (!isTauriDesktopRuntime()) {
    return { handled: false, mode: "browser" };
  }
  const state = getDesktopWindowState();
  if (!state) throw new Error("desktop_window_state_unavailable");
  const normalized = canonicalProductRoute(route);
  const targetKind = desktopWindowKindForRoute(normalized);
  if (targetKind === state.kind) {
    if (!navigateCurrentDesktopRoute(normalized, replace)) {
      throw new Error("desktop_same_window_navigation_failed");
    }
    return { handled: true, mode: "same-window" };
  }
  if (!(await openDesktopProductWindow(targetKind, normalized))) {
    throw new Error("desktop_cross_window_navigation_failed");
  }
  return { handled: true, mode: "cross-window" };
}

export async function openDesktopProductWindow(
  kind: AngmooDesktopWindowKind,
  route: string,
) {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return false;
  await invoke("open_product_window", {
    kind,
    route: canonicalProductRoute(route),
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

export async function startDesktopWindowResize(
  direction: AngmooPhoneResizeDirection,
) {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return false;
  await invoke("start_product_window_resize", { direction });
  return true;
}

export async function getDesktopRuntimeStatus() {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return null;
  return invoke<AngmooDesktopRuntimeStatus>("desktop_runtime_status");
}

export async function retryDesktopRuntime() {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return false;
  await invoke("retry_desktop_runtime");
  return true;
}

export function normalizeInternalRoute(route: string) {
  const parsed = new URL(route, "http://angmoo.local");
  if (parsed.origin !== "http://angmoo.local") {
    throw new Error("desktop_route_must_be_internal");
  }
  if (parsed.pathname === "/index.html") {
    const bootstrapRoute = parsed.searchParams.get(DESKTOP_WINDOW_ROUTE_QUERY);
    if (bootstrapRoute && bootstrapRoute !== route) {
      return normalizeInternalRoute(bootstrapRoute);
    }
    return "/";
  }
  const pathname = parsed.pathname.replace(/\/+$/, "") || "/";
  return `${pathname}${parsed.search}${parsed.hash}`;
}

export function canonicalProductRoute(route: string) {
  const normalized = normalizeInternalRoute(route);
  const parsed = new URL(normalized, "http://angmoo.local");
  let pathname = parsed.pathname;
  if (pathname === "/worlds/new") {
    pathname = "/studio/worlds/new";
  } else {
    const creatorAlias = pathname.match(/^\/worlds\/([^/]+)\/creator$/);
    if (creatorAlias) pathname = `/studio/worlds/${creatorAlias[1]}`;
  }
  return `${pathname}${parsed.search}${parsed.hash}`;
}

function routePathname(route: string) {
  return new URL(normalizeInternalRoute(route), "http://angmoo.local").pathname;
}
