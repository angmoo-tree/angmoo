"use client";

import { useAuth } from "@/hooks/use-auth";
import { CreatorStudioDashboard } from "@/features/creator-studio/components/creator-studio-dashboard";
import { getLocalWorldSurface } from "@/features/device-home/api/device-home-client";

export function StudioRouteClient() {
  const { status } = useAuth();
  return <CreatorStudioDashboard authStatus={status} getLocalWorldSurface={getLocalWorldSurface} />;
}
