"use client";

import { useEffect, useRef } from "react";

const PULL_THRESHOLD_PX = 70;
const INTERACTIVE_SELECTOR =
  'a, button, input, textarea, select, [role="button"], [contenteditable="true"]';

type MobilePullToRefreshOptions = {
  enabled?: boolean;
  refreshing: boolean;
  onRefresh: () => void | Promise<void>;
};

export function useMobilePullToRefresh({
  enabled = true,
  refreshing,
  onRefresh,
}: MobilePullToRefreshOptions) {
  const onRefreshRef = useRef(onRefresh);
  const refreshingRef = useRef(refreshing);

  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);

  useEffect(() => {
    refreshingRef.current = refreshing;
  }, [refreshing]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined" || !("ontouchstart" in window)) {
      return;
    }

    let tracking = false;
    let triggered = false;
    let startX = 0;
    let startY = 0;

    function handleTouchStart(event: TouchEvent) {
      const touch = event.touches[0];
      if (!touch || refreshingRef.current || getScrollTop() > 0 || isInteractive(event.target)) {
        tracking = false;
        return;
      }

      tracking = true;
      triggered = false;
      startX = touch.clientX;
      startY = touch.clientY;
    }

    function handleTouchMove(event: TouchEvent) {
      if (!tracking || triggered || refreshingRef.current) return;

      const touch = event.touches[0];
      if (!touch || getScrollTop() > 0) {
        tracking = false;
        return;
      }

      const deltaX = Math.abs(touch.clientX - startX);
      const deltaY = touch.clientY - startY;
      const verticalPull = deltaY > 0 && deltaY > deltaX;

      if (!verticalPull) return;

      event.preventDefault();

      if (deltaY < PULL_THRESHOLD_PX) return;

      triggered = true;
      tracking = false;
      void onRefreshRef.current();
    }

    function handleTouchEnd() {
      tracking = false;
    }

    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: false });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    window.addEventListener("touchcancel", handleTouchEnd, { passive: true });

    return () => {
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("touchcancel", handleTouchEnd);
    };
  }, [enabled]);
}

function getScrollTop() {
  return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
}

function isInteractive(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(INTERACTIVE_SELECTOR));
}
