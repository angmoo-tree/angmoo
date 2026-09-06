"use client";
import { WorldCreatorClient as WorldDefinitionEditor } from "@/features/worlds/components/world-creator-client";
import type { WorldRoleInput } from "@/features/worlds/types/worlds";
import { StudioWorldCharacterList } from "@/features/creator-studio/components/studio-world-character-list";
import { WorldPackageExportPanel } from "@/features/world-packages/public";
function renderWorldTools(worldId: string, roles: WorldRoleInput[]) {
  return <><StudioWorldCharacterList worldId={worldId} roles={roles} /><WorldPackageExportPanel worldId={worldId} /></>;
}
export function WorldCreatorClient({ worldId }: { worldId?: string }) {
  return <WorldDefinitionEditor worldId={worldId} renderWorldTools={renderWorldTools} />;
}
