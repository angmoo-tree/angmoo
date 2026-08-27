import { AppShell } from "@/components/app-shell";
import {
  getInitialSocialFeed,
  PostListClient,
  type FeedPage as FeedPageData,
} from "@/features/social/public";

type FeedPageProps = {
  suppressFeedSnippet?: boolean;
};

export async function FeedPage({
  suppressFeedSnippet = false,
}: FeedPageProps = {}) {
  let feed: FeedPageData = { items: [], next_cursor: null };
  let error: string | null = null;

  try {
    feed = await getInitialSocialFeed(10);
  } catch (err) {
    error = err instanceof Error ? err.message : "게시글을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <PostListClient
        initialFeed={feed}
        initialError={error}
        suppressFeedSnippet={suppressFeedSnippet}
      />
    </AppShell>
  );
}
