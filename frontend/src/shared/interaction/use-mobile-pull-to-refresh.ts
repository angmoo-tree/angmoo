"use client";

import { useEffect, useRef } from "react";

import { getScrollTop, resolveScrollEventTarget } from "./scroll-viewport";

const PULL_THRESHOLD_PX = 70;
const INTERACTIVE_SELECTOR =
  'a, button, input, textarea, select, [role="button"], [contenteditable="true"]';
const DEVICE_SCROLL_OWNER_SELECTOR = '[data-device-scroll-owner="true"]';

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
    const scrollTarget = resolveScrollEventTarget(
      document.querySelector<HTMLElement>(DEVICE_SCROLL_OWNER_SELECTOR),
    );

    function handleTouchStart(rawEvent: Event) {
      const event = rawEvent as TouchEvent;
      const touch = event.touches[0];
      if (
        !touch ||
        refreshingRef.current ||
        getScrollTop(scrollTarget) > 0 ||
        isInteractive(event.target)
      ) {
        tracking = false;
        return;
      }

      tracking = true;
      triggered = false;
      startX = touch.clientX;
      startY = touch.clientY;
    }

    function handleTouchMove(rawEvent: Event) {
      const event = rawEvent as TouchEvent;
      if (!tracking || triggered || refreshingRef.current) return;

      const touch = event.touches[0];
      if (!touch || getScrollTop(scrollTarget) > 0) {
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

    scrollTarget.addEventListener("touchstart", handleTouchStart, {
      passive: true,
    });
    scrollTarget.addEventListener("touchmove", handleTouchMove, {
      passive: false,
    });
    scrollTarget.addEventListener("touchend", handleTouchEnd, { passive: true });
    scrollTarget.addEventListener("touchcancel", handleTouchEnd, { passive: true });

    return () => {
      scrollTarget.removeEventListener("touchstart", handleTouchStart);
      scrollTarget.removeEventListener("touchmove", handleTouchMove);
      scrollTarget.removeEventListener("touchend", handleTouchEnd);
      scrollTarget.removeEventListener("touchcancel", handleTouchEnd);
    };
  }, [enabled]);
}

function isInteractive(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(INTERACTIVE_SELECTOR));
}
