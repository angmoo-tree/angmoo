"use client";

import { useEffect } from "react";
import {
  ANGMOO_SERVICE_WORKER_SCOPE,
  ANGMOO_SERVICE_WORKER_URL,
} from "../model/pwa-contract";

async function registerAngmooServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  const registration = await navigator.serviceWorker.register(
    ANGMOO_SERVICE_WORKER_URL,
    {
      scope: ANGMOO_SERVICE_WORKER_SCOPE,
      updateViaCache: "none",
    },
  );
  await registration.update();
}

export async function unregisterAngmooServiceWorker(): Promise<boolean> {
  if (!("serviceWorker" in navigator)) {
    return false;
  }
  const registration = await navigator.serviceWorker.getRegistration(
    ANGMOO_SERVICE_WORKER_SCOPE,
  );
  return registration ? registration.unregister() : false;
}

export function PwaServiceWorkerLifecycle() {
  useEffect(() => {
    void registerAngmooServiceWorker().catch(() => {
      // PWA installation is optional. Registration failure must not block Angmoo.
    });
  }, []);

  return null;
}
