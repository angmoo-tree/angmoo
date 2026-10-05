"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AUTH_CHANGED_EVENT, captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { useAuth } from "@/hooks/use-auth";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { setOwnerManualLike } from "../api/social-write-client";
import type { SocialPostActionPresentation } from "../types/social-presentation-contract";
import { isConfirmedReaction, publishConfirmedReaction, reconcileReactionRead, SOCIAL_REACTION_EVENT, socialReactionRevision, type ConfirmedSocialReaction, type ReactionPost } from "../utils/confirmed-reactions";

export type OwnerReactionPost = ReactionPost;
const pendingRequests = new Set<string>();

/** Only the request owner publishes; consumers apply the same server result. */
export function useOwnerReactions(scope: string, onConfirmed: (change: ConfirmedSocialReaction) => void, worldId?: string) {
  const { user, sessionRevision } = useAuth();
  const [pendingState, setPending] = useState({ scope, ids: new Set<string>() });
  const [errorState, setError] = useState({ scope, failed: false });
  const [lifetime, setLifetime] = useState(0);
  const scopeKey = JSON.stringify([scope, worldId ?? null, user?.id ?? null, sessionRevision, lifetime]);
  const callback = useRef(onConfirmed);
  const generation = useRef(0);
  const confirmed = useRef(new Map<string, ConfirmedSocialReaction>());
  useEffect(() => { callback.current = onConfirmed; }, [onConfirmed]);
  useEffect(() => {
    let ownedScope = captureAuthRequestScope();
    const changed = () => {
      if (isCurrentAuthRequestScope(ownedScope)) return;
      ownedScope = captureAuthRequestScope();
      ++generation.current; confirmed.current.clear(); setLifetime(value => value + 1);
    };
    window.addEventListener(AUTH_CHANGED_EVENT, changed);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, changed);
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    };
  }, []);
  useEffect(() => {
    const ownedGeneration = ++generation.current;
    const authScope = captureAuthRequestScope();
    confirmed.current.clear();
    function receive(event: Event) {
      const change: unknown = (event as CustomEvent<unknown>).detail;
      if (!isConfirmedReaction(change) || (worldId && change.world_id !== worldId) || !isCurrentAuthRequestScope(authScope)) return;
      const key = JSON.stringify([change.world_id, change.post_id]);
      if ((confirmed.current.get(key)?.revision ?? 0) >= change.revision) return;
      confirmed.current.set(key, change);
      callback.current(change);
    }
    window.addEventListener(SOCIAL_REACTION_EVENT, receive);
    return () => { generation.current = ownedGeneration + 1; window.removeEventListener(SOCIAL_REACTION_EVENT, receive); };
  }, [scope, worldId, user?.id, sessionRevision, lifetime]);

  const reconcilePost = useCallback(<T extends ReactionPost>(post: T, readRevision: number): T =>
    reconcileReactionRead(post, readRevision, confirmed.current), []);

  async function setReaction(post: OwnerReactionPost) {
    const actor = post.reaction_owner_world_character_id, world = post.reaction_world_id;
    if (!post.can_owner_like || !world || !actor || !["liked", "not_liked"].includes(post.viewer_like_state ?? "")) return;
    const authScope = captureAuthRequestScope();
    const requestKey = JSON.stringify([authScope.revision, authScope.userId, sessionRevision, authScope.apiBaseUrl, world, post.id, actor]);
    if (pendingRequests.has(requestKey)) return;
    const current = generation.current;
    pendingRequests.add(requestKey);
    setPending(previous => ({ scope: scopeKey, ids: new Set([...(previous.scope === scopeKey ? previous.ids : []), post.id]) }));
    setError({ scope: scopeKey, failed: false });
    try {
      const result = await setOwnerManualLike(world, post.id, actor, post.viewer_like_state !== "liked");
      if (current === generation.current && isCurrentAuthRequestScope(authScope)) publishConfirmedReaction(result);
    } catch {
      if (current === generation.current && isCurrentAuthRequestScope(authScope)) setError({ scope: scopeKey, failed: true });
    } finally {
      pendingRequests.delete(requestKey);
      if (current === generation.current && isCurrentAuthRequestScope(authScope)) {
        setPending(previous => {
          if (previous.scope !== scopeKey) return previous;
          const ids = new Set(previous.ids); ids.delete(post.id); return { scope: scopeKey, ids };
        });
      }
    }
  }
  function likeAction(post: OwnerReactionPost): SocialPostActionPresentation {
    const viewerStateKnown = post.viewer_like_state === "liked" || post.viewer_like_state === "not_liked";
    const interactive = Boolean(post.can_owner_like && post.reaction_world_id && post.reaction_owner_world_character_id && viewerStateKnown);
    return {
      kind: "like",
      interaction: interactive ? "button" : "metric",
      label: "좋아요",
      count: post.like_count,
      // Aggregate metrics retain their historical count presentation without
      // assigning a viewer selection or granting a reaction capability.
      accent: viewerStateKnown ? post.viewer_like_state === "liked" : post.like_count > 0,
      disabled: pendingState.scope === scopeKey && pendingState.ids.has(post.id),
    };
  }
  return { setReaction, likeAction, reconcilePost, captureReadRevision: socialReactionRevision, error: errorState.scope === scopeKey && errorState.failed };
}
