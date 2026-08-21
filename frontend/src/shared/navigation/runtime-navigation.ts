"use client";

import {
  usePathname as useNextPathname,
  useRouter as useNextRouter,
  useSearchParams as useNextSearchParams,
} from "next/navigation";
import { useMemo } from "react";

import { isStaticFrontendProfile } from "@/shared/runtime/public";

function staticNavigate(href: string, replace: boolean) {
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

export function useRuntimePathname() {
  const pathname = useNextPathname();
  if (isStaticFrontendProfile() && typeof window !== "undefined") {
    return window.location.pathname;
  }
  return pathname;
}

export function useRuntimeSearchParams() {
  const searchParams = useNextSearchParams();
  if (isStaticFrontendProfile() && typeof window !== "undefined") {
    return new URLSearchParams(window.location.search);
  }
  return searchParams;
}
