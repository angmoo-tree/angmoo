"use client";

import { Minus, X } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

import {
  type AngmooPhoneResizeDirection,
  consumeDesktopWindowBootstrapRoute,
  currentDesktopRoute,
  desktopWindowKindForRoute,
  getDesktopWindowState,
  invokeDesktopWindowCommand,
  isTauriDesktopRuntime,
  navigateCurrentDesktopRoute,
  openDesktopProductWindow,
  startDesktopWindowResize,
} from "./product-window";
import styles from "./desktop-window-controls.module.css";

const WINDOW_DRAG_INTERACTIVE_SELECTOR = [
  "a[href]",
  "button",
  "input",
  "textarea",
  "select",
  "option",
  "label",
  "[contenteditable]:not([contenteditable='false'])",
  "[role='button']",
  "[role='link']",
  "[role='tab']",
  "[role='checkbox']",
  "[role='radio']",
  "[role='slider']",
  "[role='textbox']",
  "[role='menuitem']",
  "[data-window-drag-disabled='true']",
].join(",");

const PHONE_RESIZE_EDGE_THICKNESS = 8;
const PHONE_CORNER_RADIUS_MIN = 26;
const PHONE_CORNER_RADIUS_MAX = 42;
const PHONE_CORNER_RADIUS_WIDTH_RATIO = 0.0725;

function phoneResizeDirectionAtPoint(
  x: number,
  y: number,
  width: number,
  height: number,
): AngmooPhoneResizeDirection | null {
  if (x < 0 || y < 0 || x >= width || y >= height) return null;

  const radius = Math.min(
    PHONE_CORNER_RADIUS_MAX,
    Math.max(PHONE_CORNER_RADIUS_MIN, width * PHONE_CORNER_RADIUS_WIDTH_RATIO),
    width / 2,
    height / 2,
  );
  const edge = Math.min(PHONE_RESIZE_EDGE_THICKNESS, radius);
  const cornerDirection = (
    centerX: number,
    centerY: number,
    direction: AngmooPhoneResizeDirection,
  ) => {
    const distance = Math.hypot(x - centerX, y - centerY);
    return distance >= radius - edge && distance <= radius + edge ? direction : null;
  };

  if (x < radius + edge && y < radius + edge) {
    return cornerDirection(radius, radius, "north-west");
  }
  if (x >= width - radius - edge && y < radius + edge) {
    return cornerDirection(width - radius, radius, "north-east");
  }
  if (x < radius + edge && y >= height - radius - edge) {
    return cornerDirection(radius, height - radius, "south-west");
  }
  if (x >= width - radius - edge && y >= height - radius - edge) {
    return cornerDirection(width - radius, height - radius, "south-east");
  }

  if (y <= edge && x >= radius - edge && x <= width - radius + edge) return "north";
  if (y >= height - edge && x >= radius - edge && x <= width - radius + edge) {
    return "south";
  }
  if (x <= edge && y >= radius - edge && y <= height - radius + edge) return "west";
  if (x >= width - edge && y >= radius - edge && y <= height - radius + edge) {
    return "east";
  }
  return null;
}

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
    const windowKind = state.kind;
    window.__ANGMOO_DESKTOP_WINDOW__ = state;
    consumeDesktopWindowBootstrapRoute(state);
    document.body.dataset.angmooDesktopWindow = windowKind;
    if (windowKind === "phone") {
      document.body.dataset.angmooWindowDrag = "manual";
    }

    function resizeDirection(event: PointerEvent) {
      return phoneResizeDirectionAtPoint(
        event.clientX,
        event.clientY,
        window.innerWidth,
        window.innerHeight,
      );
    }

    function clearResizeCursor() {
      delete document.documentElement.dataset.angmooWindowResize;
    }

    function handlePointerMove(event: PointerEvent) {
      if (
        windowKind !== "phone" ||
        event.pointerType !== "mouse" ||
        event.buttons !== 0
      ) {
        return;
      }
      const direction = resizeDirection(event);
      if (direction) {
        document.documentElement.dataset.angmooWindowResize = direction;
      } else {
        clearResizeCursor();
      }
    }

    function handlePointerDown(event: PointerEvent) {
      if (
        windowKind !== "phone" ||
        event.defaultPrevented ||
        !event.isPrimary ||
        event.pointerType !== "mouse" ||
        event.button !== 0 ||
        event.buttons !== 1 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      const direction = resizeDirection(event);
      if (direction) {
        event.preventDefault();
        event.stopImmediatePropagation();
        void startDesktopWindowResize(direction).catch(() => {
          // Keep the Phone usable when a host cannot begin native resize.
        });
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(WINDOW_DRAG_INTERACTIVE_SELECTOR)) return;
      const selection = window.getSelection();
      if (selection && !selection.isCollapsed) return;

      event.preventDefault();
      void invokeDesktopWindowCommand("start_product_window_drag").catch(() => {
        // The surface remains usable if the host refuses a native drag.
      });
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

    document.addEventListener("pointerdown", handlePointerDown, true);
    document.addEventListener("pointermove", handlePointerMove, true);
    document.documentElement.addEventListener("pointerleave", clearResizeCursor);
    window.addEventListener("blur", clearResizeCursor);
    document.addEventListener("click", handleClick, true);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true);
      document.removeEventListener("pointermove", handlePointerMove, true);
      document.documentElement.removeEventListener("pointerleave", clearResizeCursor);
      window.removeEventListener("blur", clearResizeCursor);
      document.removeEventListener("click", handleClick, true);
      clearResizeCursor();
      delete document.body.dataset.angmooDesktopWindow;
      delete document.body.dataset.angmooWindowDrag;
    };
  }, []);

  if (!active) return null;
  return (
    <div
      className={styles.controls}
      data-window-drag-disabled="true"
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
