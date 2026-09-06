import { fetchBackendJson } from "@/lib/server/backend";
import type { FeedPage } from "@/features/social/types/social-feed-contract";

export async function getInitialSocialFeed(limit = 10): Promise<FeedPage> {
  return fetchBackendJson<FeedPage>(`/api/v1/feed?limit=${limit}`);
}

