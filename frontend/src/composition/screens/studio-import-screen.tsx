"use client";

import { useAuth } from "@/hooks/use-auth";
import { WorldPackageImportClient } from "@/features/world-packages/components/world-package-import-client";

export function StudioImportRouteClient() {
  const { status } = useAuth();
  return <WorldPackageImportClient authStatus={status} />;
}
