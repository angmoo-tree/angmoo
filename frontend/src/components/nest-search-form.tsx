"use client";

import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

export function NestSearchForm({
  initialQuery = "",
  className = "",
  inputClassName = "",
  autoFocus = false,
  scope = "nest",
}: {
  initialQuery?: string;
  className?: string;
  inputClassName?: string;
  autoFocus?: boolean;
  scope?: "nest" | "tree";
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const scopedInitialQuery =
    scope === "tree" ? searchParams.get("q") ?? "" : initialQuery;
  const [query, setQuery] = useState(scopedInitialQuery);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = query.trim();
    if (scope === "tree") {
      const tab = searchParams.get("tab") ?? "notice";
      const params = new URLSearchParams({ tab });
      if (nextQuery) params.set("q", nextQuery);
      router.push(`/tree?${params.toString()}`);
      return;
    }
    if (!nextQuery) {
      router.push("/search");
      return;
    }
    const params = new URLSearchParams({ q: nextQuery, tab: "posts" });
    router.push(`/search?${params.toString()}`);
  }

  return (
    <form onSubmit={handleSubmit} className={`relative w-full ${className}`}>
      <div className="pointer-events-none absolute inset-y-0 left-5 flex items-center">
        <Search size={22} className="text-[#98a2b3]" />
      </div>
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={scope === "tree" ? "나무 검색" : "둥지 검색"}
        autoFocus={autoFocus}
        className={`h-12 w-full rounded-full border border-[#e1e5eb] bg-white pl-12 pr-5 text-[16px] font-bold text-[#667085] outline-none focus:border-[#ff6b6b] focus:ring-1 focus:ring-[#ff6b6b] ${inputClassName}`}
      />
    </form>
  );
}
