"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { DeviceHome } from "@/features/device-home/components/device-home";
import { getProductRuntimeState } from "@/features/runtime-status/api/runtime-status-client";
import { RuntimeStatusSummary } from "@/features/runtime-status/components/runtime-status-summary";
import type { ProductRuntimeState } from "@/features/runtime-status/types/runtime-status";
import { DeviceHomeShell } from "@/composition/screens/device-home-shell";

export function DeviceHomeScreen() {
  const { status } = useAuth();
  const [runtimeState, setRuntimeState] = useState<ProductRuntimeState>("stale_state");
  useEffect(() => {
    if (status !== "authenticated") return;
    const controller = new AbortController();
    getProductRuntimeState({ signal: controller.signal })
      .then(setRuntimeState)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRuntimeState("stale_state");
      });
    return () => controller.abort();
  }, [status]);
  return (
    <DeviceHomeShell status={<RuntimeStatusSummary state={runtimeState} />}>
      <DeviceHome authStatus={status} />
    </DeviceHomeShell>
  );
}
