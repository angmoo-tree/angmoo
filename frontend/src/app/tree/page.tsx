import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { TreeCommunityClient } from "@/components/tree-community-client";
import { fetchBackendJson } from "@/lib/backend";
import type { TreeCategory, TreeFeedPage } from "@/lib/tree";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "나무 | Angmoo",
  description: "앵무 주인들이 공지, 질문, 제안, 이야기를 나누는 Angmoo 커뮤니티입니다.",
  alternates: {
    canonical: "/tree",
  },
};

type PageProps = {
  searchParams: Promise<{
    tab?: string | string[];
    q?: string | string[];
  }>;
};

const EMPTY_PAGE: TreeFeedPage = { items: [], next_cursor: null };

export default async function TreePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const category = readCategory(params.tab);
  const query = readParam(params.q).trim();
  const apiParams = new URLSearchParams({ category, limit: "10" });
  if (query) apiParams.set("q", query);

  let page: TreeFeedPage = EMPTY_PAGE;
  let error: string | null = null;

  try {
    page = await fetchBackendJson<TreeFeedPage>(
      `/api/v1/tree/posts?${apiParams.toString()}`,
    );
  } catch (err) {
    error = err instanceof Error ? err.message : "나무 글을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <TreeCommunityClient
        key={`${category}:${query}`}
        initialPage={page}
        initialCategory={category}
        initialQuery={query}
        initialError={error}
      />
    </AppShell>
  );
}

function readParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

function readCategory(value: string | string[] | undefined): TreeCategory {
  const raw = readParam(value);
  if (
    raw === "bug" ||
    raw === "suggestion" ||
    raw === "question" ||
    raw === "free"
  ) {
    return raw;
  }
  return "notice";
}
