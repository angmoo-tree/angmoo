import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { TreePostDetailClient } from "@/components/tree-post-detail-client";
import { fetchBackendJson } from "@/lib/backend";
import type { TreePostDetail } from "@/lib/tree";
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
      canonical: `/tree/${postId}`,
    },
  };
}

export default async function TreePostPage({ params }: PageProps) {
  const { postId } = await params;
  let post: TreePostDetail | null = null;
  let error: string | null = null;

  try {
    post = await fetchBackendJson<TreePostDetail>(`/api/v1/tree/posts/${postId}`);
  } catch (err) {
    error = err instanceof Error ? err.message : "나무 글을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <TreePostDetailClient
        postId={postId}
        initialPost={post}
        initialError={error}
      />
    </AppShell>
  );
}
