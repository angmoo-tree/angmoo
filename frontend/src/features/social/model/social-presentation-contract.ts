import type {
  MentionedCharacterRef,
  PostMediaRead,
} from "./social-feed-contract";

export type SocialPostActionKind = "reply" | "repost" | "like" | "share";

/**
 * A visible action is always supplied by an adapter that owns the underlying
 * capability. An omitted count stays omitted; presentation code must not turn
 * missing payload data into a synthetic zero.
 */
export type SocialPostActionPresentation = {
  kind: SocialPostActionKind;
  label: string;
  count?: number;
  href?: string;
  accent?: boolean;
};

/**
 * Product-neutral social row data shared by the global and World-scoped feed
 * adapters. Optional fields remain optional so a smaller World payload cannot
 * accidentally claim a hosted/global capability.
 */
export type SocialPostPresentation = {
  id: string;
  authorName: string;
  authorHandle?: string | null;
  authorAvatarUrl?: string | null;
  createdAt: string;
  timeLabel: string;
  title: string;
  body: string;
  mentionedCharacters?: MentionedCharacterRef[];
  media?: PostMediaRead[];
};
