"use client";

import { useUiText } from "@/hooks/use-ui-text";
import type { ProductRuntimeState } from "@/features/runtime-status/types/runtime-status";
import { StatusChip } from "@/components/ui/status";

import { presentRuntimeState } from "@/features/runtime-status/utils/runtime-status-presentation";

type RuntimeStatusSummaryProps = {
  state: ProductRuntimeState;
};

export function RuntimeStatusSummary({ state }: RuntimeStatusSummaryProps) {
  const uiText = useUiText("runtime-status");
  const presentation = presentRuntimeState(state);
  const label = uiText(presentation.label);
  const description = uiText(presentation.description);
  return (
    <StatusChip
      aria-label={uiText("로컬 runtime: {{value0}}. {{value1}}", {value0: label, value1: description})}
      data-runtime-state={state}
      label={label}
      title={description}
      tone={presentation.tone}
    />
  );
}
