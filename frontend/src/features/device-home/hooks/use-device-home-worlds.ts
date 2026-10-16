"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DeviceHomeApiError, getLocalWorldSurface } from "@/features/device-home/api/device-home-client";
import { ApiRequestError } from "@/lib/http/api-request";
import { createDeviceHomeWorldController } from "./device-home-world-controller";

export function isTransientHomeReadError(error: unknown) {
  if (error instanceof DeviceHomeApiError && error.message === "world_surface_schema_mismatch") return false;
  return error instanceof TypeError ||
    ((error instanceof DeviceHomeApiError || error instanceof ApiRequestError) && error.status >= 500);
}

export function useDeviceHomeWorlds(authenticated: boolean, ready: boolean, ensure?: () => Promise<unknown>) {
  const [controller] = useState(() => createDeviceHomeWorldController({
    ensure: ensure ?? (() => Promise.resolve()), read: signal => getLocalWorldSurface("device_home", { signal }),
    captureScope: () => { const scope = captureAuthRequestScope(); return () => isCurrentAuthRequestScope(scope); },
    transient: isTransientHomeReadError,
  }));
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => {
    if (!authenticated) return;
    controller.activate(ready, document.visibilityState !== "hidden");
    const visibility = () => controller.visibility(document.visibilityState !== "hidden");
    window.addEventListener("focus", controller.resume);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      controller.deactivate(); window.removeEventListener("focus", controller.resume);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [authenticated, ready, controller]);
  return { ...snapshot, retry: controller.retry };
}
