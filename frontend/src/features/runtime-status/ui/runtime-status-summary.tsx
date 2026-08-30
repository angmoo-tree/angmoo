import { StatusChip } from "@/shared/ui/public";

import {
  presentRuntimeState,
  type ProductRuntimeState,
} from "../model/runtime-status-contract";

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
