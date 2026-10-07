"use client";
import { useUiText } from "@/hooks/use-ui-text";


import { useEffect, useRef, useState } from "react";
import { getDesktopShutdownStatus, isTauriDesktopRuntime, skipDesktopMemoryShutdown, type DesktopShutdownStatus } from "@/lib/desktop/product-window";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

export function DesktopShutdownOverlay() {
  const uiText = useUiText("shell");
  const [status, setStatus] = useState<DesktopShutdownStatus | null>(null);
  const [skipping, setSkipping] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!isTauriDesktopRuntime()) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const value = await getDesktopShutdownStatus(); if (active && value) setStatus(value); }
      catch { /* A stopped host needs no browser error surface. */ }
      if (active) timer = setTimeout(poll, 250);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, []);
  return <Dialog title={uiText("끄는 중…")} description={uiText("접수한 경험을 기억으로 저장하고 검색 자료를 준비합니다.")} open={status !== null && status.phase !== "RUNNING"} onOpenChange={() => {}} closeOnBackdrop={false} closeOnEscape={false} closeButtonAttributes={{ hidden: true }} initialFocusRef={button} dialogAttributes={{ style: { margin: "auto" } }}
    actions={<Button ref={button} variant="secondary" disabled={skipping} onClick={() => { setSkipping(true); void skipDesktopMemoryShutdown().catch(() => setSkipping(false)); }}>{uiText("지금 종료")}</Button>}>
    <p role="status">{skipping || status?.deferred ? uiText("남은 기억 저장은 다음 실행에서 이어집니다.") : uiText("기억을 저장하고 있어요. 잠시만 기다려 주세요.")}</p>
  </Dialog>;
}
