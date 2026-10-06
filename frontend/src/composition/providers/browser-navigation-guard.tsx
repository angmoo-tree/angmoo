"use client";

import { useEffect } from "react";
import { confirmProductLeave } from "@/lib/desktop/navigation-guard";
import { isTauriDesktopRuntime } from "@/lib/desktop/product-window";
import { isStaticFrontendProfile } from "@/lib/runtime/runtime-config";

/** Apply registered draft guards before ordinary browser links enter Next navigation. */
export function BrowserNavigationGuard() {
  useEffect(() => {
    if (isStaticFrontendProfile() || isTauriDesktopRuntime()) return;
    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self")) return;
      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin ||
          destination.pathname + destination.search === window.location.pathname + window.location.search) return;
      if (!confirmProductLeave()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };
    document.addEventListener("click", click, true);
    return () => document.removeEventListener("click", click, true);
  }, []);
  return null;
}
