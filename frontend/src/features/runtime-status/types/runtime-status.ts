export type ProductRuntimeState =
  | "degraded"
  | "failed"
  | "healthy"
  | "recovery_required"
  | "stale_state"
  | "starting"
  | "stopped"
  | "stopping";

export type ProductRuntimePresentation = {
  description: string;
  label: string;
  tone:
    | "danger"
    | "degraded"
    | "disabled"
    | "healthy"
    | "neutral"
    | "running"
    | "waiting";
};

