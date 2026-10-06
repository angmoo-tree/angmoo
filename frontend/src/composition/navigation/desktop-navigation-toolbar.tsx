"use client";

import { ArrowLeft, ArrowRight, Home, RotateCw } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useUiText } from "@/hooks/use-ui-text";
import { desktopHistoryAvailability } from "@/lib/desktop/desktop-history";
import { confirmProductLeave } from "@/lib/desktop/navigation-guard";
import { currentDesktopRoute, DESKTOP_NAVIGATION_ERROR_EVENT, navigateDesktopProductRoute, reloadDesktopProductRoute, subscribeDesktopRoute } from "@/lib/desktop/product-window";
import styles from "./desktop-navigation-toolbar.module.css";

export function DesktopNavigationToolbar() {
  const uiText = useUiText("shell");
  const route = useSyncExternalStore(subscribeDesktopRoute, currentDesktopRoute, () => "/");
  const history = useSyncExternalStore(subscribeDesktopRoute, () => JSON.stringify(desktopHistoryAvailability()), () => '{"back":false,"forward":false}');
  const available = JSON.parse(history) as { back: boolean; forward: boolean };
  const input = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const action = (work: () => Promise<unknown> | unknown) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(false);
    void Promise.resolve().then(work).catch(() => setError(true)).finally(() => { inFlight.current = false; setBusy(false); });
  };
  const travel = (forward: boolean) => {
    const permitted = desktopHistoryAvailability();
    if ((forward ? permitted.forward : permitted.back) && confirmProductLeave()) window.history[forward ? "forward" : "back"]();
  };
  useEffect(() => {
    const fail = () => setError(true);
    const shortcut = (event: KeyboardEvent) => {
      const modalOpen = [...document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]')]
        .some(dialog => dialog.getClientRects().length > 0 && dialog.getAttribute("aria-hidden") !== "true");
      if (event.isComposing || modalOpen || inFlight.current) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target?.closest('textarea, [contenteditable="true"]')) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "l") {
        event.preventDefault(); input.current?.focus(); input.current?.select();
      } else if (event.key === "F5" || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "r")) {
        event.preventDefault(); reloadDesktopProductRoute();
      } else if (event.altKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
        event.preventDefault();
        const forward = event.key === "ArrowRight", available = desktopHistoryAvailability();
        if ((forward ? available.forward : available.back) && confirmProductLeave()) window.history[forward ? "forward" : "back"]();
      }
    };
    window.addEventListener(DESKTOP_NAVIGATION_ERROR_EVENT, fail);
    window.addEventListener("keydown", shortcut);
    return () => { window.removeEventListener(DESKTOP_NAVIGATION_ERROR_EVENT, fail); window.removeEventListener("keydown", shortcut); };
  }, []);
  return (
    <nav aria-label={uiText("Angmoo 탐색")} aria-busy={busy} className={styles.toolbar} data-desktop-navigation="true">
      <button aria-label={uiText("뒤로")} className={styles.button} disabled={busy || !available.back} onClick={() => travel(false)} title={uiText("뒤로")} type="button"><ArrowLeft size={20} /></button>
      <button aria-label={uiText("앞으로")} className={styles.button} disabled={busy || !available.forward} onClick={() => travel(true)} title={uiText("앞으로")} type="button"><ArrowRight size={20} /></button>
      <button aria-label={uiText("현재 화면 새로고침")} className={styles.button} disabled={busy} onClick={() => action(reloadDesktopProductRoute)} title={uiText("현재 화면 새로고침")} type="button"><RotateCw size={20} /></button>
      <button aria-label={uiText("Device Home으로 이동")} className={styles.button} disabled={busy} onClick={() => action(() => navigateDesktopProductRoute("/"))} title={uiText("Device Home으로 이동")} type="button"><Home size={20} /></button>
      <form className={styles.form} onSubmit={event => {
        event.preventDefault();
        // Enter during IME composition must not commit an unfinished route.
        action(async () => { await navigateDesktopProductRoute(draft); input.current?.blur(); });
      }}>
        <input aria-label={uiText("Angmoo 내부 경로")} aria-describedby={error ? "desktop-navigation-error" : undefined} aria-invalid={error || undefined} autoComplete="off" className={styles.address} readOnly={busy} ref={input} spellCheck={false} value={editing ? draft : route}
          onChange={event => setDraft(event.target.value)} onFocus={() => { setDraft(route); setEditing(true); }} onBlur={() => setEditing(false)}
          onKeyDown={event => {
            if (event.nativeEvent.isComposing && event.key === "Enter") event.preventDefault();
            if (event.key === "Escape" && !event.nativeEvent.isComposing) { setDraft(route); setError(false); input.current?.blur(); }
          }} />
      </form>
      {error ? <p className={styles.error} id="desktop-navigation-error" role="alert">{uiText("경로를 열 수 없습니다. 지원하는 Angmoo 내부 경로를 확인해주세요.")}</p> : null}
    </nav>
  );
}
