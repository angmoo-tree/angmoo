import { fetchBackendJson } from "@/lib/backend";
import type { FeedPage } from "@/lib/community";

export async function getInitialSocialFeed(limit = 10): Promise<FeedPage> {
  return fetchBackendJson<FeedPage>(`/api/v1/feed?limit=${limit}`);
}
