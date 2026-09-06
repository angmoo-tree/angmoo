"use client";

import { updateUserFeedPreferences } from "@/features/identity/api/session";
import { PostListClient } from "@/composition/screens/post-list-screen";
import { type FeedPage } from "@/features/social/types/social-feed-contract";

export function PostFeedScreen(props: {
  initialFeed: FeedPage;
  initialError: string | null;
  suppressFeedSnippet?: boolean;
}) {
  return <PostListClient {...props} updateUserFeedPreferences={updateUserFeedPreferences} />;
}
