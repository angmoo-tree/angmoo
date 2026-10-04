"use client";

import { useEffect, useRef } from "react";
import { isProductUnloadApproved, registerProductLeaveGuard } from "@/lib/desktop/navigation-guard";
import { useUiText } from "@/hooks/use-ui-text";

export function useProductLeaveGuard(pending: boolean) {
  const uiText = useUiText("shell");
  const release = useRef<(() => void) | null>(null);
  useEffect(() => {
    if (!pending) return;
    const unregister = registerProductLeaveGuard(() => window.confirm(uiText("저장하지 않은 입력이나 진행 중인 작업이 있습니다. 이 화면을 떠날까요?")));
    const beforeUnload = (event: BeforeUnloadEvent) => { if (!isProductUnloadApproved()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", beforeUnload);
    const cleanup = () => { unregister(); window.removeEventListener("beforeunload", beforeUnload); };
    release.current = cleanup;
    return cleanup;
  }, [pending, uiText]);
  // An owner can release its confirmation after a successful durable save,
  // before its own canonical redirect. React has not necessarily committed yet.
  return () => { release.current?.(); };
}
