import { isSupportedProductRoute } from "@/lib/navigation/product-route-validation";
import { desktopHistoryAvailability } from "@/lib/desktop/desktop-history";
import { approveProductUnload, confirmProductLeave } from "@/lib/desktop/navigation-guard";

export type AngmooDesktopWindowKind =
  | "memory"
  | "phone"
  | "studio"
  | "relationship-graph";

export type AngmooDesktopWindowState = {
  kind: AngmooDesktopWindowKind;
  route: string;
};

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

export type DesktopShutdownStatus = { phase: "RUNNING" | "QUIESCING" | "PREPARING" | "CONSOLIDATING" | "FINALIZING" | "EXIT_READY"; deferred: boolean };

export async function getDesktopShutdownStatus(): Promise<DesktopShutdownStatus | null> {
  if (!isTauriDesktopRuntime()) return null;
  const value = await window.__TAURI__?.core?.invoke?.<DesktopShutdownStatus>("desktop_shutdown_status");
  if (!value || !["RUNNING", "QUIESCING", "PREPARING", "CONSOLIDATING", "FINALIZING", "EXIT_READY"].includes(value.phase) || typeof value.deferred !== "boolean") return null;
  return value;
}

export async function skipDesktopMemoryShutdown() {
  if (isTauriDesktopRuntime()) await window.__TAURI__?.core?.invoke?.("skip_memory_shutdown");
}

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
export const DESKTOP_NAVIGATE_EVENT = "angmoo:desktop-navigate";
export const DESKTOP_NAVIGATION_ERROR_EVENT = "angmoo:desktop-navigation-error";
const DESKTOP_WINDOW_KINDS = new Set<AngmooDesktopWindowKind>([
  "memory",
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
  const bootstrap = desktopWindowStateFromBootstrapQuery();
  const initial = window.__ANGMOO_DESKTOP_WINDOW__ ?? bootstrap;
  if (!initial && !isTauriDesktopRuntime()) return null;
  const kind = initial?.kind ?? "phone";
  // A document-start initialization script describes the first opening only.
  // A real deep URL wins on reload; consume the encoded index bootstrap once.
  const raw = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const route = bootstrap?.route ?? canonicalProductRoute(raw);
  return { kind, route };
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
      route: validateInternalProductRoute(route),
    };
  } catch {
    return null;
  }
}

export function consumeDesktopWindowBootstrapRoute(
  state: AngmooDesktopWindowState,
) {
  if (typeof window === "undefined") return;
  window.__ANGMOO_DESKTOP_WINDOW__ = state;
  const params = new URLSearchParams(window.location.search);
  if (
    !params.has(DESKTOP_WINDOW_KIND_QUERY) &&
    !params.has(DESKTOP_WINDOW_ROUTE_QUERY)
  ) {
    return;
  }
  window.history.replaceState(window.history.state, "", state.route);
}

export function desktopWindowKindForRoute(
  route: string,
): AngmooDesktopWindowKind {
  const pathname = routePathname(canonicalProductRoute(route));
  if (pathname === "/memory") return "memory";
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
  const handlePopState = () => {
    onStoreChange();
  };
  window.addEventListener(DESKTOP_ROUTE_EVENT, onStoreChange);
  window.addEventListener("popstate", handlePopState);
  return () => {
    window.removeEventListener(DESKTOP_ROUTE_EVENT, onStoreChange);
    window.removeEventListener("popstate", handlePopState);
  };
}

export function publishDesktopRoute() {
  if (isTauriDesktopRuntime()) {
    const state = getDesktopWindowState();
    if (state) window.__ANGMOO_DESKTOP_WINDOW__ = state;
  }
  window.dispatchEvent(new Event(DESKTOP_ROUTE_EVENT));
}

export function navigateCurrentDesktopRoute(route: string, replace = false) {
  if (!isTauriDesktopRuntime()) return false;
  const state = getDesktopWindowState();
  const normalized = validateInternalProductRoute(route);
  if (!state || desktopWindowKindForRoute(normalized) !== state.kind) return false;
  if (!replace && normalized === state.route) return true;
  if (document.documentElement.dataset.angmooRuntimeProfile !== "tauri-static") {
    window.dispatchEvent(new CustomEvent(DESKTOP_NAVIGATE_EVENT, { detail: { route: normalized, replace } }));
  } else {
    window.history[replace ? "replaceState" : "pushState"](window.history.state, "", normalized);
    publishDesktopRoute();
  }
  return true;
}

export function navigateBackCurrentDesktopRoute(fallbackRoute: string) {
  if (!isTauriDesktopRuntime()) return false;
  if (!confirmProductLeave()) return true;
  if (desktopHistoryAvailability().back) { window.history.back(); return true; }
  void navigateDesktopProductRoute(fallbackRoute, true, true).catch(reportDesktopNavigationError);
  return true;
}

export function reportDesktopNavigationError() {
  window.dispatchEvent(new Event(DESKTOP_NAVIGATION_ERROR_EVENT));
}

export function reloadDesktopProductRoute() {
  if (!confirmProductLeave()) return false;
  approveProductUnload();
  window.location.reload();
  return true;
}

export async function navigateDesktopProductRoute(
  route: string,
  replace = false,
  leaveConfirmed = false,
): Promise<DesktopProductNavigationResult> {
  if (!isTauriDesktopRuntime()) {
    return { handled: false, mode: "browser" };
  }
  const state = getDesktopWindowState();
  if (!state) throw new Error("desktop_window_state_unavailable");
  const normalized = validateInternalProductRoute(route);
  const targetKind = desktopWindowKindForRoute(normalized);
  if (targetKind === state.kind) {
    await window.__TAURI__?.core?.invoke?.("validate_product_navigation", { kind: targetKind, route: normalized });
    if (normalized !== state.route && !leaveConfirmed && !confirmProductLeave()) return { handled: true, mode: "same-window" };
    if (!navigateCurrentDesktopRoute(normalized, replace)) {
      throw new Error("desktop_same_window_navigation_failed");
    }
    return { handled: true, mode: "same-window" };
  }
  // open_product_window already validates kind/route before creating or
  // focusing its singleton. Do not perform the same host validation twice.
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
    route: validateInternalProductRoute(route),
  });
  return true;
}

export async function invokeDesktopWindowCommand(
  command: "close_product_window",
) {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) return false;
  await invoke(command);
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
  if (route.length > 1024 || !route.startsWith("/") || route.startsWith("//") || Array.from(route).some(ch => ch.charCodeAt(0) < 32 || ch.charCodeAt(0) === 92)) throw new Error("desktop_route_must_be_internal");
  const path = route.split(/[?#]/, 1)[0];
  for (const part of path.split("/")) {
    const decoded = decodeURIComponent(part);
    if (decoded === "." || decoded === ".." || Array.from(decoded).some(ch => ch.charCodeAt(0) < 32 || ch === "/" || ch.charCodeAt(0) === 92)) throw new Error("invalid_product_route_segment");
  }
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
  if (pathname === "/memory-explorer") {
    pathname = "/memory";
  } else if (pathname === "/worlds/new") {
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

export function validateInternalProductRoute(route: string) {
  if (/__angmoo_|(?:api[_-]?key|launch[_-]?token|access[_-]?token)=/i.test(route)) throw new Error("private_product_route");
  const normalized = canonicalProductRoute(route);
  const parsed = new URL(normalized, "http://angmoo.local");
  if (parsed.hash || [...parsed.searchParams.keys()].some(key => key.toLowerCase().startsWith("__angmoo_") || ["apikey", "launchtoken", "accesstoken"].includes(key.toLowerCase().replace(/[_-]/g, "")))) throw new Error("private_product_route");
  if (!isSupportedProductRoute(normalized)) throw new Error("unsupported_product_route");
  return normalized;
}

export async function openExternalProductLink(url: string) {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error("invalid_external_product_link");
  await window.__TAURI__?.core?.invoke?.("open_external_product_link", { url: parsed.href });
}
