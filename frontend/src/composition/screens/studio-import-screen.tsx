"use client";

import { useAuth } from "@/hooks/use-auth";
import { WorldPackageImportClient } from "@/features/world-packages/public";

export function StudioImportRouteClient() {
  const { status } = useAuth();
  return <WorldPackageImportClient authStatus={status} />;
}
