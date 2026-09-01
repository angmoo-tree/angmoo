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
} from "@/shared/desktop/public";
import { isStaticFrontendProfile } from "@/shared/runtime/public";

function staticNavigate(href: string, replace: boolean) {
  if (isTauriDesktopRuntime()) {
    void navigateDesktopProductRoute(href, replace).catch(() => undefined);
    return;
  }
  if (replace) window.location.replace(href);
  else window.location.assign(href);
}

export function useRuntimeRouter() {
  const router = useNextRouter();
  return useMemo(() => {
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
