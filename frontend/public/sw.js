const ANGMOO_WORKER_VERSION = "angmoo-pwa-shell-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "ANGMOO_SKIP_WAITING") {
    self.skipWaiting();
    return;
  }
  if (event.data?.type === "ANGMOO_WORKER_VERSION") {
    event.source?.postMessage({
      type: "ANGMOO_WORKER_VERSION",
      version: ANGMOO_WORKER_VERSION,
    });
  }
});
