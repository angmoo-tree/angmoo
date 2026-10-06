import { expect, test } from "@playwright/test";
import { applyConfirmedReaction, isConfirmedReaction, reconcileReactionRead, type ConfirmedSocialReaction } from "../frontend/src/features/social/utils/confirmed-reactions";

const confirmed: ConfirmedSocialReaction = { world_id: "world-a", post_id: "post-a", owner_world_character_id: "owner-a",
  viewer_like_state: "liked", like_count: 19, can_owner_like: true, revision: 3 };
const post = { id: "post-a", world_id: "world-a", like_count: 7, viewer_like_state: "not_liked" as const,
  reaction_world_id: "world-a", reaction_owner_world_character_id: "owner-a", can_owner_like: true, media: [{ url: "/media/retained.png" }], body: "Original content" };

test("T14/T25: canonical count is exact and duplicate application retains identity", () => {
  const updated = applyConfirmedReaction(post, confirmed);
  expect(updated.like_count).toBe(19); expect(updated.viewer_like_state).toBe("liked");
  expect(updated.media).toBe(post.media); expect(updated.body).toBe(post.body);
  expect(applyConfirmedReaction(updated, confirmed)).toBe(updated);
});
test("T28: equal post IDs in different Worlds and actors keep scope and capability", () => {
  const otherWorld = { ...post, world_id: "world-b" };
  expect(applyConfirmedReaction(otherWorld, confirmed)).toBe(otherWorld);
  const otherActor = { ...post, reaction_owner_world_character_id: "owner-b", can_owner_like: false };
  const updated = applyConfirmedReaction(otherActor, confirmed);
  expect(updated.like_count).toBe(19); expect(updated.viewer_like_state).toBe("not_liked"); expect(updated.can_owner_like).toBe(false);
  const unsupported = { id: "post-a", like_count: 7, can_owner_like: false };
  expect(applyConfirmedReaction(unsupported, confirmed)).toBe(unsupported);
});
test("T26: an older GET is overlaid, a later canonical GET remains authoritative", () => {
  const ledger = new Map([[JSON.stringify(["world-a", "post-a"]), confirmed]]);
  expect(reconcileReactionRead(post, 2, ledger).like_count).toBe(19);
  const fresh = { ...post, like_count: 23 };
  expect(reconcileReactionRead(fresh, 3, ledger)).toBe(fresh);
  expect(reconcileReactionRead({ ...post, world_id: "world-b" }, 2, ledger).like_count).toBe(7);
});
test("T23: malformed notification data is rejected", () => {
  expect(isConfirmedReaction(confirmed)).toBe(true);
  for (const value of [null, {}, { ...confirmed, like_count: -1 }, { ...confirmed, like_count: 1.5 },
    { ...confirmed, viewer_like_state: "unavailable" }, { ...confirmed, revision: 0 }, { ...confirmed, can_owner_like: false }]) expect(isConfirmedReaction(value)).toBe(false);
});
