export function resolvedLegacyWorldChatRouteParts(thread: {
  id: string;
  requester_world_character_id: string | null;
  responding_world_character_id: string | null;
  world_id: string | null;
  world_scope_status: "resolved" | "ambiguous" | "quarantined";
}): { threadId: string; worldId: string } | null {
  if (
    thread.world_scope_status !== "resolved" ||
    !thread.world_id ||
    !thread.requester_world_character_id ||
    !thread.responding_world_character_id
  ) {
    return null;
  }
  return { threadId: thread.id, worldId: thread.world_id };
}
