"use client";

import { useAuth } from "@/hooks/use-auth";
import { CreatorStudioDashboard } from "@/features/creator-studio/components/creator-studio-dashboard";
import { getLocalWorldSurface } from "@/features/device-home/api/device-home-client";
import { WorldDeleteControl } from "@/features/worlds/components/world-delete-control";
import { WorldDeletionProgressList } from "@/features/worlds/components/world-deletion-progress";
import { WorldPackageExportPanel } from "@/features/world-packages/components/world-package-export-panel";
import { useCallback, useState } from "react";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";

export function StudioRouteClient() {
  const { status } = useAuth();
  const identity = useAuthRuntimeIdentity("studio");
  return <ScopedStudio key={identity} status={status} />;
}

function ScopedStudio({ status }: { status: "checking" | "authenticated" | "unauthenticated" }) {
  const [revision, setRevision] = useState(0);
  const [excluded, setExcluded] = useState<string[]>([]);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  return <CreatorStudioDashboard authStatus={status} getLocalWorldSurface={getLocalWorldSurface} refreshRevision={revision} excludedWorldIds={excluded}
    deletionProgress={status === "authenticated" ? <WorldDeletionProgressList revision={revision} onCompleted={refresh} /> : null}
    renderWorldActions={world => <WorldDeleteControl worldId={world.world_id} canDelete={world.can_delete} isDefaultSpace={world.is_default_space} renderExport={id => <WorldPackageExportPanel worldId={id} />}
      onAccepted={receipt => { setExcluded(value => [...value, receipt.world_id]); refresh(); }} />} />;
}
