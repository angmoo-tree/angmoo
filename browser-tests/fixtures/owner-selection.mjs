/** Explicit selected read used by fixtures; absent/deleted/forbidden stay separate. */
export function selectedOwnerRead(actor) {
  return { schema_version: "owner-character-selection-v1", world_id: actor.world_id,
    state: "selected", actor };
}
