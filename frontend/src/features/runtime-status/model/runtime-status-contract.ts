export type ProductRuntimeState =
  | "blocked"
  | "degraded"
  | "healthy"
  | "stale_state"
  | "starting"
  | "stopped"
  | "stopping";

export type ProductRuntimePresentation = {
  label: string;
  tone: "blocked" | "degraded" | "healthy" | "neutral";
};

const RUNTIME_PRESENTATIONS: Record<ProductRuntimeState, ProductRuntimePresentation> = {
  blocked: { label: "확인 필요", tone: "blocked" },
  degraded: { label: "일부 기능 제한", tone: "degraded" },
  healthy: { label: "정상", tone: "healthy" },
  stale_state: { label: "상태 확인 중", tone: "neutral" },
  starting: { label: "시작 중", tone: "neutral" },
  stopped: { label: "중지됨", tone: "blocked" },
  stopping: { label: "종료 중", tone: "neutral" },
};

export function presentRuntimeState(
  state: ProductRuntimeState,
): ProductRuntimePresentation {
  return RUNTIME_PRESENTATIONS[state];
}
