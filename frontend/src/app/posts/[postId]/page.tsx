import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { PostDetailClient } from "@/components/post-detail-client";
import { fetchBackendJson } from "@/lib/backend";
import type { PostThreadRead } from "@/lib/community";
import { NO_INDEX_FOLLOW_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{
    postId: string;
  }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { postId } = await params;
  return {
    robots: NO_INDEX_FOLLOW_ROBOTS,
    alternates: {
      canonical: `/posts/${postId}`,
    },
  };
}

export default async function PostDetailPage({ params }: PageProps) {
  const { postId } = await params;
  let thread: PostThreadRead | null = null;
  let error: string | null = null;

  try {
    thread = await fetchBackendJson<PostThreadRead>(
      `/api/v1/posts/${postId}/thread`,
    );
  } catch (err) {
    error = err instanceof Error ? err.message : "게시글을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <PostDetailClient
        postId={postId}
        initialThread={thread}
        initialError={error}
      />
    </AppShell>
  );
}
