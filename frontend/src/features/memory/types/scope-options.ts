/** Display inputs for the owner Memory scope selector, loaded by the product screen. */
export type MemoryWorldOption = {world_id: string; name: string; launchable: boolean};
export type MemoryCharacterOption = {world_character_id: string; display_name: string; avatar_url: string | null};
export type MemoryScopeLoaders = {
  getLocalWorldSurface: (surface: "device_home", options: {signal: AbortSignal}) => Promise<{items: MemoryWorldOption[]}>;
  listWorldCharacterProfiles: (worldId: string, options: {signal: AbortSignal}) => Promise<{items: MemoryCharacterOption[]}>;
};
