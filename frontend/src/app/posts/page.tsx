import type { Metadata } from "next";

import { FeedPage } from "@/app/feed-page";
import { NO_INDEX_FOLLOW_ROBOTS } from "@/config/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_FOLLOW_ROBOTS,
  alternates: {
    canonical: "/posts",
  },
};

export default async function PostsPage() {
  return <FeedPage />;
}
