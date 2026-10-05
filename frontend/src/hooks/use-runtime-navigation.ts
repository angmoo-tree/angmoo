"use client";

import {
  usePathname as useNextPathname,
  useRouter as useNextRouter,
  useSearchParams as useNextSearchParams,
} from "next/navigation";
import { useCallback, useMemo } from "react";

import {
  currentDesktopRoute,
  isTauriDesktopRuntime,
  navigateBackCurrentDesktopRoute,
  navigateDesktopProductRoute,
  publishDesktopRoute,
  reportDesktopNavigationError,
} from "@/lib/desktop/product-window";
import { isStaticFrontendProfile } from "@/lib/runtime/runtime-config";

function navigateStaticBrowserQuery(href: string, replace: boolean): boolean {
  const destination = new URL(href, window.location.href);
  if (destination.origin === window.location.origin &&
      destination.pathname === window.location.pathname &&
      destination.search !== window.location.search &&
      destination.hash === window.location.hash) {
    // A query-only view change belongs to the current static React surface.
    // Keep its pending writes alive and notify the existing route subscriber.
    window.history[replace ? "replaceState" : "pushState"](window.history.state, "", href);
    publishDesktopRoute();
    return true;
  }
  return false;
}

function staticNavigate(href: string, replace: boolean) {
  if (isTauriDesktopRuntime()) {
    void navigateDesktopProductRoute(href, replace).catch(reportDesktopNavigationError);
    return;
  }
  if (navigateStaticBrowserQuery(href, replace)) return;
  if (replace) window.location.replace(href);
  else window.location.assign(href);
}

export function useRuntimeRouter() {
  const router = useNextRouter();
  return useMemo(() => {
    if (typeof window !== "undefined" && isTauriDesktopRuntime() && !isStaticFrontendProfile()) {
      return { ...router,
        push: (href: string) => { void navigateDesktopProductRoute(href).catch(reportDesktopNavigationError); },
        replace: (href: string) => { void navigateDesktopProductRoute(href, true).catch(reportDesktopNavigationError); },
      };
    }
    if (!isStaticFrontendProfile() || typeof window === "undefined") {
      return router;
    }
    return {
      back: () => window.history.back(),
      forward: () => window.history.forward(),
      prefetch: async () => undefined,
      push: (href: string) => staticNavigate(href, false),
      refresh: () => window.location.reload(),
      replace: (href: string) => staticNavigate(href, true),
    };
  }, [router]);
}

export function useRuntimeBack(fallbackHref: string) {
  const router = useRuntimeRouter();
  return useCallback(() => {
    if (isTauriDesktopRuntime()) {
      if (navigateBackCurrentDesktopRoute(fallbackHref)) return;
      staticNavigate(fallbackHref, true);
      return;
    }
    router.back();
  }, [fallbackHref, router]);
}

export function useRuntimePathname() {
  const pathname = useNextPathname();
  if (isStaticFrontendProfile() && typeof window !== "undefined") {
    return new URL(currentDesktopRoute(), "http://angmoo.local").pathname;
  }
  return pathname;
}

export function useRuntimeSearchParams() {
  const searchParams = useNextSearchParams();
  if (isStaticFrontendProfile() && typeof window !== "undefined") {
    return new URL(currentDesktopRoute(), "http://angmoo.local").searchParams;
  }
  return searchParams;
}
