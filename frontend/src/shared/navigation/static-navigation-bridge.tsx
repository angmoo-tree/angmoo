"use client";

import { useEffect } from "react";

import { isStaticFrontendProfile } from "@/shared/runtime/public";

export function StaticNavigationBridge() {
  useEffect(() => {
    if (!isStaticFrontendProfile()) return;

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
      event.preventDefault();
      event.stopImmediatePropagation();
      // Static/Tauri navigation intentionally reloads through the route fallback.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(
        `${destination.pathname}${destination.search}${destination.hash}`,
      );
    }

    document.addEventListener("click", handleClick, true);
    return () => document.removeEventListener("click", handleClick, true);
  }, []);

  return null;
}
