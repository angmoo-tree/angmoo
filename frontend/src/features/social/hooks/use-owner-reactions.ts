"use client";
import { useEffect, useRef, useState } from "react";
import { setOwnerManualLike } from "../api/social-write-client";
import type { SocialPostActionPresentation } from "../types/social-presentation-contract";

export type OwnerReactionPost = { id: string; like_count: number; viewer_like_state?: "liked" | "not_liked" | "unavailable"; can_owner_like?: boolean; reaction_world_id?: string | null; reaction_owner_world_character_id?: string | null };

/** Social owns invalidation. A context must come from the server, never the active character. */
export function useOwnerReactions(scope: string, refresh: () => void, worldId?: string) {
  const scopeKey = JSON.stringify([scope, worldId ?? null]);
  const [pendingState, setPending] = useState({scopeKey, ids: new Set<string>()});
  const [errorState, setError] = useState({scopeKey, failed: false});
  const pendingRef = useRef(new Map<string, Set<string>>());
  const pending = pendingState.scopeKey === scopeKey ? pendingState.ids : new Set<string>();
  const error = errorState.scopeKey === scopeKey && errorState.failed;
  const refreshRef = useRef(refresh);
  const generation = useRef(0);
  useEffect(() => { refreshRef.current = refresh; });
  useEffect(() => {
    const ownedGeneration = ++generation.current;
    function invalidate(event: Event) {
      const context = (event as CustomEvent).detail;
      if (context && (!worldId || context.worldId === worldId)) refreshRef.current();
    }
    window.addEventListener("angmoo-social-reaction", invalidate);
    return () => { generation.current = ownedGeneration + 1; window.removeEventListener("angmoo-social-reaction", invalidate); };
  }, [scope, worldId]);
  async function setReaction(post: OwnerReactionPost) {
    const actor = post.reaction_owner_world_character_id, world = post.reaction_world_id;
    if (!post.can_owner_like || !world || !actor || !["liked", "not_liked"].includes(post.viewer_like_state ?? "")) return;
    const ownedPending = pendingRef.current.get(scopeKey) ?? new Set<string>();
    if (ownedPending.has(post.id)) return;
    const current = generation.current;
    pendingRef.current.set(scopeKey, ownedPending);
    ownedPending.add(post.id); setPending({scopeKey, ids: new Set(ownedPending)}); setError({scopeKey, failed: false});
    try { await setOwnerManualLike(world, post.id, actor, post.viewer_like_state !== "liked"); }
    catch { if (current === generation.current) setError({scopeKey, failed: true}); }
    finally {
      ownedPending.delete(post.id);
      if (ownedPending.size === 0) pendingRef.current.delete(scopeKey);
      // Release this request's lock even after navigation. It cannot clear a
      // different scope's active lock or replace its source/error state.
      setPending(previous => previous.scopeKey === scopeKey ? {scopeKey, ids: new Set(ownedPending)} : previous);
    }
  }
  function likeAction(post: OwnerReactionPost): SocialPostActionPresentation {
    return {kind: "like", interaction: post.can_owner_like && post.reaction_world_id && post.reaction_owner_world_character_id && ["liked", "not_liked"].includes(post.viewer_like_state ?? "") ? "button" : "metric",
      label: "좋아요", count: post.like_count, accent: post.viewer_like_state === "liked", disabled: pending.has(post.id)};
  }
  return {setReaction, likeAction, error};
}
