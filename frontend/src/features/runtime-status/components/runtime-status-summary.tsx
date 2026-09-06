import type { ProductRuntimeState } from "@/features/runtime-status/types/runtime-status";
import { StatusChip } from "@/components/ui/status";

import { presentRuntimeState } from "@/features/runtime-status/utils/runtime-status-presentation";

type RuntimeStatusSummaryProps = {
  state: ProductRuntimeState;
};

export function RuntimeStatusSummary({ state }: RuntimeStatusSummaryProps) {
  const presentation = presentRuntimeState(state);
  return (
    <StatusChip
      aria-label={`로컬 runtime: ${presentation.label}. ${presentation.description}`}
      data-runtime-state={state}
      label={presentation.label}
      title={presentation.description}
      tone={presentation.tone}
    />
  );
}
