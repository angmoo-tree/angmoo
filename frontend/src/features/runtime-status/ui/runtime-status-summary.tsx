import { StatusBadge } from "@/shared/ui/public";

import {
  presentRuntimeState,
  type ProductRuntimeState,
} from "../model/runtime-status-contract";

type RuntimeStatusSummaryProps = {
  state: ProductRuntimeState;
};

export function RuntimeStatusSummary({ state }: RuntimeStatusSummaryProps) {
  const presentation = presentRuntimeState(state);
  return <StatusBadge label={presentation.label} tone={presentation.tone} />;
}
