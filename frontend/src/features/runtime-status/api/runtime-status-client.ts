import type { ProductRuntimeState } from "../model/runtime-status-contract";
import { runtimeFetch } from "@/shared/runtime/public";


type RuntimeStatusEnvelope = {
  schema_version: "local-runtime-status-v1";
  installation_state:
    | "stopped"
    | "starting"
    | "ready"
    | "degraded"
    | "stopping"
    | "recovery_required"
    | "failed";
};

const PRODUCT_STATE: Record<
  RuntimeStatusEnvelope["installation_state"],
  ProductRuntimeState
> = {
  stopped: "stopped",
  starting: "starting",
  ready: "healthy",
  degraded: "degraded",
  stopping: "stopping",
  recovery_required: "blocked",
  failed: "blocked",
};

export async function getProductRuntimeState(
  options: { signal?: AbortSignal } = {},
): Promise<ProductRuntimeState> {
  const response = await runtimeFetch("/api/backend/runtime/status", {
    cache: "no-store",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  if (!response.ok) {
    return response.status >= 500 ? "degraded" : "stale_state";
  }
  const payload = (await response.json().catch(() => null)) as Partial<RuntimeStatusEnvelope> | null;
  if (
    payload?.schema_version !== "local-runtime-status-v1" ||
    !payload.installation_state ||
    !(payload.installation_state in PRODUCT_STATE)
  ) {
    return "stale_state";
  }
  return PRODUCT_STATE[payload.installation_state];
}
