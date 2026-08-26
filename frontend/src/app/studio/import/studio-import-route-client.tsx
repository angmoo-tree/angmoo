"use client";

import { useAuth } from "@/components/auth-provider";
import { WorldPackageImportClient } from "@/features/world-packages/public";

export function StudioImportRouteClient() {
  const { status } = useAuth();
  return <WorldPackageImportClient authStatus={status} />;
}
