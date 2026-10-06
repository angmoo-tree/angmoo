import type { ManualSocialLikeRead } from "../types/social-write-contract";

export const SOCIAL_REACTION_EVENT = "angmoo-social-reaction";
export type ConfirmedSocialReaction = ManualSocialLikeRead & { revision: number };
export type ReactionPost = {
  id: string;
  world_id?: string;
  like_count: number;
  viewer_like_state?: "liked" | "not_liked" | "unavailable";
  can_owner_like?: boolean;
  reaction_world_id?: string | null;
  reaction_owner_world_character_id?: string | null;
};

// A document-local notification sequence, not a post cache. Consumers keep
// only the confirmed results needed to fence their in-flight GETs.
let revision = 0;
export function socialReactionRevision() { return revision; }

export function publishConfirmedReaction(result: ManualSocialLikeRead) {
  const change: ConfirmedSocialReaction = { ...result, revision: ++revision };
  window.dispatchEvent(new CustomEvent<ConfirmedSocialReaction>(SOCIAL_REACTION_EVENT, { detail: change }));
}

export function isConfirmedReaction(value: unknown): value is ConfirmedSocialReaction {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<ConfirmedSocialReaction>;
  return typeof result.world_id === "string" && typeof result.post_id === "string"
    && typeof result.owner_world_character_id === "string"
    && (result.viewer_like_state === "liked" || result.viewer_like_state === "not_liked")
    && Number.isInteger(result.like_count) && Number(result.like_count) >= 0
    && result.can_owner_like === true && Number.isInteger(result.revision) && Number(result.revision) > 0;
}

export function reactionPostKey(post: ReactionPost) {
  const world = post.world_id ?? post.reaction_world_id;
  return world ? JSON.stringify([world, post.id]) : null;
}

export function applyConfirmedReaction<T extends ReactionPost>(post: T, change: ConfirmedSocialReaction): T {
  if (post.id !== change.post_id || (post.world_id ?? post.reaction_world_id) !== change.world_id) return post;
  // Aggregate belongs to the post; viewer selection belongs to the exact
  // server-provided actor. A result never creates a write capability.
  const ownsSelection = post.reaction_owner_world_character_id === change.owner_world_character_id;
  if (post.like_count === change.like_count && (!ownsSelection || post.viewer_like_state === change.viewer_like_state)) return post;
  return { ...post, like_count: change.like_count,
    ...(ownsSelection ? { viewer_like_state: change.viewer_like_state } : {}) };
}

export function reconcileReactionRead<T extends ReactionPost>(post: T, readRevision: number, confirmed: ReadonlyMap<string, ConfirmedSocialReaction>): T {
  const key = reactionPostKey(post);
  const change = key ? confirmed.get(key) : undefined;
  return change && change.revision > readRevision ? applyConfirmedReaction(post, change) : post;
}
