"use client";

import { useEffect } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { installDesktopHistory } from "@/lib/desktop/desktop-history";
import { consumeDesktopWindowBootstrapRoute, getDesktopWindowState, isTauriDesktopRuntime, navigateDesktopProductRoute, openExternalProductLink, publishDesktopRoute, reportDesktopNavigationError, DESKTOP_NAVIGATE_EVENT } from "@/lib/desktop/product-window";

/** Own native integration only; ordinary browser navigation remains Next's. */
export function DesktopWindowBridge() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    if (isTauriDesktopRuntime()) publishDesktopRoute();
  }, [pathname, search]);
  useEffect(() => {
    if (!isTauriDesktopRuntime()) return;
    const state = getDesktopWindowState();
    if (!state) return;
    consumeDesktopWindowBootstrapRoute(state);
    document.body.dataset.angmooDesktopWindow = state.kind;
    // Next installs its own history integration in the parent effect. Wrap
    // that settled integration so its initial replace cannot erase our entry.
    let active = true;
    let removeHistory: (() => void) | undefined;
    queueMicrotask(() => {
      if (active) removeHistory = installDesktopHistory(publishDesktopRoute);
    });
    const requested = (event: Event) => {
      const detail = (event as CustomEvent<{ route: string; replace?: boolean; native?: boolean }>).detail;
      if (!detail) return;
      if (detail.native) {
        void navigateDesktopProductRoute(detail.route).catch(reportDesktopNavigationError);
      } else {
        router[detail.replace ? "replace" : "push"](detail.route);
      }
    };
    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.hasAttribute("download")) return;
      let url: URL;
      try { url = new URL(anchor.href, window.location.href); } catch { return; }
      if (url.origin !== window.location.origin) {
        event.preventDefault(); event.stopPropagation();
        void openExternalProductLink(url.href).catch(reportDesktopNavigationError);
        return;
      }
      event.preventDefault(); event.stopPropagation();
      void navigateDesktopProductRoute(`${url.pathname}${url.search}${url.hash}`).catch(reportDesktopNavigationError);
    };
    window.addEventListener(DESKTOP_NAVIGATE_EVENT, requested);
    document.addEventListener("click", click, true);
    return () => {
      active = false;
      removeHistory?.();
      window.removeEventListener(DESKTOP_NAVIGATE_EVENT, requested);
      document.removeEventListener("click", click, true);
      delete document.body.dataset.angmooDesktopWindow;
    };
  }, [router]);
  return null;
}
