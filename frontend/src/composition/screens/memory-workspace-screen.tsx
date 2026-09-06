"use client";

import { listWorldCharacterProfiles } from "@/features/characters/api/world-character-profile-client";
import { getLocalWorldSurface } from "@/features/device-home/api/device-home-client";
import { MemoryWorkspace, type MemoryWorkspaceProps } from "@/features/memory/components/memory-workspace";
import type { MemoryScopeLoaders } from "@/features/memory/types/scope-options";

export function MemoryWorkspaceScreen(props: Omit<MemoryWorkspaceProps, keyof MemoryScopeLoaders>) {
  return <MemoryWorkspace {...props} getLocalWorldSurface={getLocalWorldSurface} listWorldCharacterProfiles={listWorldCharacterProfiles} />;
}
