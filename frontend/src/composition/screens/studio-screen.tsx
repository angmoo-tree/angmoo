"use client";

import { useAuth } from "@/hooks/use-auth";
import { CreatorStudioDashboard } from "@/features/creator-studio/public";

export function StudioRouteClient() {
  const { status } = useAuth();
  return <CreatorStudioDashboard authStatus={status} />;
}
