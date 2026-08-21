"use client";

import { Minus, X } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

import {
  currentDesktopRoute,
  desktopWindowKindForRoute,
  getDesktopWindowState,
  invokeDesktopWindowCommand,
  isTauriDesktopRuntime,
  navigateCurrentDesktopRoute,
  openDesktopProductWindow,
} from "./product-window";
import styles from "./desktop-window-controls.module.css";

export function DesktopWindowBridge() {
  const active = useSyncExternalStore(
    () => () => undefined,
    isTauriDesktopRuntime,
    () => false,
  );

  useEffect(() => {
    if (!isTauriDesktopRuntime()) return;
    const state = getDesktopWindowState();
    if (!state) return;
    window.__ANGMOO_DESKTOP_WINDOW__ = state;
    document.body.dataset.angmooDesktopWindow = state.kind;
    if (state.kind === "phone") {
      document.body.setAttribute("data-tauri-drag-region", "deep");
    }

    function handleClick(event: MouseEvent) {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;

      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      const route = `${destination.pathname}${destination.search}${destination.hash}`;
      const targetKind = desktopWindowKindForRoute(route);
      const currentKind = getDesktopWindowState()?.kind ?? "phone";

      if (targetKind === currentKind) {
        if (process.env.NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE === "tauri-static") {
          event.preventDefault();
          event.stopImmediatePropagation();
          navigateCurrentDesktopRoute(route);
        }
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      void openDesktopProductWindow(targetKind, route).catch(() => {
        // A Tauri command failure keeps the current product state intact. The
        // PR M recovery surface will make runtime failures user-actionable.
      });
    }

    document.addEventListener("click", handleClick, true);
    return () => {
      document.removeEventListener("click", handleClick, true);
      delete document.body.dataset.angmooDesktopWindow;
      document.body.removeAttribute("data-tauri-drag-region");
    };
  }, []);

  if (!active) return null;
  return (
    <div
      className={styles.controls}
      data-tauri-drag-region="false"
      data-window-route={currentDesktopRoute()}
    >
      <button
        aria-label="Angmoo 창 이동"
        className={styles.dragHandle}
        onMouseDown={() => void invokeDesktopWindowCommand("start_product_window_drag")}
        type="button"
      >
        <span aria-hidden="true" />
      </button>
      <button
        aria-label="Angmoo 창 최소화"
        className={styles.windowButton}
        onClick={() => void invokeDesktopWindowCommand("minimize_product_window")}
        type="button"
      >
        <Minus aria-hidden="true" size={14} strokeWidth={2.2} />
      </button>
      <button
        aria-label="Angmoo 창 닫기"
        className={`${styles.windowButton} ${styles.closeButton}`}
        onClick={() => void invokeDesktopWindowCommand("close_product_window")}
        type="button"
      >
        <X aria-hidden="true" size={14} strokeWidth={2.2} />
      </button>
    </div>
  );
}
