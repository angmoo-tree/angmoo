import { fetchBackendJson } from "@/lib/server/backend";
import type { FeedPage } from "../model/social-feed-contract";

export async function getInitialSocialFeed(limit = 10): Promise<FeedPage> {
  return fetchBackendJson<FeedPage>(`/api/v1/feed?limit=${limit}`);
}

