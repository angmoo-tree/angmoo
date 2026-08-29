"use client";

import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { DeviceShell, LocalDeviceNavigation } from "@/features/device-shell/public";
import {
  useRuntimePathname as usePathname,
  useRuntimeRouter as useRouter,
} from "@/shared/navigation/public";
import { isStaticFrontendProfile } from "@/shared/runtime/public";

/**
 * Compatibility facade for legacy route wrappers. UI-C keeps the import
 * stable while delegating Phone chrome, safe-area navigation, and scroll
 * ownership to the feature-owned DeviceShell.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { status, user } = useAuth();

  useEffect(() => {
    if (!pathname || status === "checking") return;
    if (
      user &&
      !user.profile_setup_completed &&
      !isStaticFrontendProfile() &&
      pathname !== "/profile/setup" &&
      pathname !== "/login"
    ) {
      router.replace("/profile/setup");
      return;
    }
    if (status === "unauthenticated" && pathname !== "/login") {
      const returnTo = pathname !== "/" ? `?returnTo=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${returnTo}`);
    }
  }, [pathname, router, status, user]);

  return (
    <DeviceShell
      ariaLabel="Angmoo Local Phone"
      navigation={<LocalDeviceNavigation />}
      surface="local-phone"
    >
      {children}
    </DeviceShell>
  );
}
