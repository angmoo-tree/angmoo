import { AppShell } from "@/components/app-shell";
import { PostListClient } from "@/components/post-list-client";
import { fetchBackendJson } from "@/lib/backend";
import type { FeedPage as FeedPageData } from "@/lib/community";

type FeedPageProps = {
  suppressFeedSnippet?: boolean;
};

export async function FeedPage({
  suppressFeedSnippet = false,
}: FeedPageProps = {}) {
  let feed: FeedPageData = { items: [], next_cursor: null };
  let error: string | null = null;

  try {
    feed = await fetchBackendJson<FeedPageData>("/api/v1/feed?limit=10");
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
