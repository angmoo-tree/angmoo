"use client";

import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/hooks/use-auth";
import { DeviceShell } from "@/components/layout/device-shell";
import { LocalDeviceNavigation } from "@/composition/shells/local-device-navigation";
import { useRuntimePathname as usePathname, useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import { isStaticFrontendProfile } from "@/lib/runtime/runtime-config";

/**
 * Shared Phone screen composition. Authentication/profile redirects and the
 * product navigation are assembled here; DeviceShell renders the supplied
 * slots and retains the established chrome, safe-area and scroll ownership.
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
