import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { SearchResultsClient } from "@/components/search-results-client";
import { fetchBackendJson } from "@/lib/backend";
import type { SearchResults } from "@/lib/community";
import { NO_INDEX_FOLLOW_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_FOLLOW_ROBOTS,
  alternates: {
    canonical: "/search",
  },
};

type SearchTab = "posts" | "characters";

type PageProps = {
  searchParams: Promise<{
    q?: string | string[];
    tab?: string | string[];
  }>;
};

const EMPTY_RESULTS: SearchResults = {
  query: "",
  posts: [],
  characters: [],
  posts_next_offset: null,
  characters_next_offset: null,
};

export default async function SearchPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const query = readParam(params.q).trim();
  const activeTab = readTab(params.tab);
  let results: SearchResults = { ...EMPTY_RESULTS, query };
  let error: string | null = null;

  if (query) {
    try {
      const apiParams = new URLSearchParams({ q: query, limit: "10" });
      results = await fetchBackendJson<SearchResults>(
        `/api/v1/search?${apiParams.toString()}`,
      );
    } catch (err) {
      error = err instanceof Error ? err.message : "검색 결과를 불러오지 못했습니다.";
    }
  }

  return (
    <AppShell>
      <SearchResultsClient
        key={`${query}:${activeTab}`}
        query={query}
        activeTab={activeTab}
        results={results}
        error={error}
      />
    </AppShell>
  );
}

function readParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function readTab(value: string | string[] | undefined): SearchTab {
  return readParam(value) === "characters" ? "characters" : "posts";
}
