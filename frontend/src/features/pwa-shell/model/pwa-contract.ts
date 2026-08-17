export const ANGMOO_SERVICE_WORKER_URL = "/sw.js";
export const ANGMOO_SERVICE_WORKER_SCOPE = "/";

export type AngmooPwaDisplayMode = "browser" | "standalone";

export function detectAngmooPwaDisplayMode(): AngmooPwaDisplayMode {
  if (typeof window === "undefined") {
    return "browser";
  }
  return window.matchMedia("(display-mode: standalone)").matches
    ? "standalone"
    : "browser";
}
