import { isTauriDesktopRuntime } from "@/shared/desktop/public";

type TauriInvoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

type DestinationSelection = {
  cancelled: boolean;
  destinationToken?: string | null;
};

function invoke(): TauriInvoke {
  const current = window.__TAURI__?.core?.invoke;
  if (!current) throw new Error("tauri_world_package_delivery_unavailable");
  return current;
}

export function supportsNativeWorldPackageSaveAs() {
  return isTauriDesktopRuntime();
}

export function selectNativeWorldPackageDestination(recommendedFilename: string) {
  return invoke()<DestinationSelection>("select_world_package_export_destination", {
    recommendedFilename,
  });
}

export function writeNativeWorldPackageDestination(
  destinationToken: string,
  bytes: Uint8Array,
) {
  return invoke()<void>("write_world_package_export_destination", {
    destinationToken,
    content: Array.from(bytes),
  });
}

export function discardNativeWorldPackageDestination(destinationToken: string) {
  return invoke()<void>("discard_world_package_export_destination", {
    destinationToken,
  });
}
