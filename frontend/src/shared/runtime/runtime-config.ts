const STATIC_FRONTEND_PROFILE = "tauri-static";
const DEFAULT_STATIC_API_BASE = "http://127.0.0.1:8080";

export type AngmooRuntimeConfig = {
  apiBaseUrl: string;
  launchToken?: string;
  profile: typeof STATIC_FRONTEND_PROFILE;
};

declare global {
  interface Window {
    __ANGMOO_RUNTIME_CONFIG__?: AngmooRuntimeConfig;
  }
}

export function isStaticFrontendProfile() {
  return (
    process.env.NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE ===
    STATIC_FRONTEND_PROFILE
  );
}

function assertLoopbackApiBase(value: string) {
  const parsed = new URL(value);
  const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]"]);
  if (
    parsed.protocol !== "http:" ||
    !loopbackHosts.has(parsed.hostname) ||
    parsed.username ||
    parsed.password ||
    (parsed.pathname !== "" && parsed.pathname !== "/")
  ) {
    throw new Error("Angmoo runtime API base must be an HTTP loopback URL.");
  }
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

export function getRuntimeConfig(): AngmooRuntimeConfig | null {
  if (!isStaticFrontendProfile()) return null;
  const injected =
    typeof window === "undefined" ? undefined : window.__ANGMOO_RUNTIME_CONFIG__;
  const apiBaseUrl = assertLoopbackApiBase(
    injected?.apiBaseUrl ??
      process.env.NEXT_PUBLIC_ANGMOO_RUNTIME_API_BASE ??
      DEFAULT_STATIC_API_BASE,
  );
  return {
    apiBaseUrl,
    launchToken: injected?.launchToken,
    profile: STATIC_FRONTEND_PROFILE,
  };
}

export function installDesktopRuntimeConfig(
  apiBaseUrl: string,
  launchToken: string,
) {
  if (typeof window === "undefined") return;
  const normalizedBase = assertLoopbackApiBase(apiBaseUrl);
  if (launchToken.length < 32) {
    throw new Error("Angmoo desktop launch token is invalid.");
  }
  window.__ANGMOO_RUNTIME_CONFIG__ = {
    apiBaseUrl: normalizedBase,
    launchToken,
    profile: STATIC_FRONTEND_PROFILE,
  };
}

export function clearDesktopRuntimeConfig() {
  if (typeof window !== "undefined") {
    delete window.__ANGMOO_RUNTIME_CONFIG__;
  }
}

export function resolveRuntimeRequestUrl(input: string) {
  const runtime = getRuntimeConfig();
  if (!runtime) return input;
  if (input.startsWith("/api/backend")) {
    return `${runtime.apiBaseUrl}/api/v1${input.slice("/api/backend".length)}`;
  }
  if (input === "/media" || input.startsWith("/media/")) {
    return `${runtime.apiBaseUrl}${input}`;
  }
  return input;
}

export async function runtimeFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
) {
  if (typeof input !== "string") return fetch(input, init);
  const runtime = getRuntimeConfig();
  if (!runtime) return fetch(input, init);

  const resolvedInput = resolveRuntimeRequestUrl(input);
  const isSidecarRequest =
    resolvedInput === runtime.apiBaseUrl ||
    resolvedInput.startsWith(`${runtime.apiBaseUrl}/`);
  const headers = new Headers(init.headers);
  if (runtime.launchToken && isSidecarRequest) {
    headers.set("X-Angmoo-Launcher-Token", runtime.launchToken);
  }
  return fetch(resolvedInput, {
    ...init,
    credentials: isSidecarRequest
      ? init.credentials === "omit"
        ? "omit"
        : "include"
      : init.credentials,
    headers,
  });
}

export function resolveRuntimeMediaUrl(path: string) {
  if (path !== "/media" && !path.startsWith("/media/")) return path;
  return resolveRuntimeRequestUrl(path);
}
