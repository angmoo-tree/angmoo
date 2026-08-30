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

const RUNTIME_PRESENTATIONS: Record<ProductRuntimeState, ProductRuntimePresentation> = {
  degraded: {
    description: "로컬 runtime의 일부 기능을 사용할 수 없습니다.",
    label: "일부 기능 제한",
    tone: "degraded",
  },
  failed: {
    description: "로컬 runtime 실행이 실패했습니다. 설정에서 상태를 확인해주세요.",
    label: "실행 실패",
    tone: "danger",
  },
  healthy: {
    description: "로컬 runtime이 준비되었습니다.",
    label: "준비됨",
    tone: "healthy",
  },
  recovery_required: {
    description: "로컬 runtime을 다시 사용하려면 복구가 필요합니다.",
    label: "복구 필요",
    tone: "danger",
  },
  stale_state: {
    description: "로컬 runtime 상태를 확인하고 있습니다.",
    label: "상태 확인 중",
    tone: "neutral",
  },
  starting: {
    description: "로컬 runtime을 시작하고 있습니다.",
    label: "시작 중",
    tone: "running",
  },
  stopped: {
    description: "로컬 runtime이 중지되어 있습니다.",
    label: "중지됨",
    tone: "disabled",
  },
  stopping: {
    description: "로컬 runtime을 안전하게 종료하고 있습니다.",
    label: "종료 중",
    tone: "waiting",
  },
};

export function presentRuntimeState(
  state: ProductRuntimeState,
): ProductRuntimePresentation {
  return RUNTIME_PRESENTATIONS[state];
}
