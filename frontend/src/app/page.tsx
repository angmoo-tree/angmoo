import { FeedPage } from "./feed-page";

export const dynamic = "force-dynamic";

export default function Home() {
  return <FeedPage suppressFeedSnippet />;
}
