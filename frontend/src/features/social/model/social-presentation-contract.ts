import type {
  MentionedCharacterRef,
  PostMediaRead,
} from "./social-feed-contract";

export type SocialPostActionKind = "reply" | "repost" | "like" | "share";

/**
 * Adapters must describe whether a slot is navigational, mutating, or a
 * read-only metric. An omitted count stays omitted; presentation code must not
 * turn missing payload data into a synthetic zero.
 */
type SocialPostActionBase = {
  kind: SocialPostActionKind;
  label: string;
  count?: number;
  accent?: boolean;
};

export type SocialPostActionPresentation =
  | (SocialPostActionBase & {
      interaction: "link";
      href: string;
    })
  | (SocialPostActionBase & {
      interaction: "button";
    })
  | (SocialPostActionBase & {
      interaction: "metric";
      count: number;
    });

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
