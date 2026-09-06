"use client";

import { updateUserFeedPreferences } from "@/features/identity/api/session";
import { PostListClient, type FeedPage } from "@/features/social/public";

export function PostFeedScreen(props: {
  initialFeed: FeedPage;
  initialError: string | null;
  suppressFeedSnippet?: boolean;
}) {
  return <PostListClient {...props} updateUserFeedPreferences={updateUserFeedPreferences} />;
}
