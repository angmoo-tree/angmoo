"use client";

import { useEffect, useRef, useState } from "react";
import { getDesktopShutdownStatus, isTauriDesktopRuntime, skipDesktopMemoryShutdown, type DesktopShutdownStatus } from "@/shared/desktop/public";
import { Button, Dialog } from "@/shared/ui/public";

export function DesktopShutdownOverlay() {
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
  return <Dialog title="끄는 중…" description="저장된 경험의 기억 정리를 마무리하고 있습니다." open={status !== null && status.phase !== "RUNNING"} onOpenChange={() => {}} closeOnBackdrop={false} closeOnEscape={false} closeButtonAttributes={{ hidden: true }} initialFocusRef={button} dialogAttributes={{ style: { margin: "auto" } }}
    actions={<Button ref={button} variant="secondary" disabled={skipping} onClick={() => { setSkipping(true); void skipDesktopMemoryShutdown().catch(() => setSkipping(false)); }}>지금 종료</Button>}>
    <p role="status">{skipping || status?.deferred ? "남은 기억 정리는 다음 실행에서 이어집니다." : "기억을 정리하고 있어요. 잠시만 기다려 주세요."}</p>
  </Dialog>;
}
