"use client";

import { useAuth } from "@/components/auth-provider";
import { CreatorStudioDashboard } from "@/features/creator-studio/public";

export function StudioRouteClient() {
  const { status } = useAuth();
  return <CreatorStudioDashboard authStatus={status} />;
}
