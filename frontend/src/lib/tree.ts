import { getStoredToken } from "@/lib/agents";

export type TreeCategory = "notice" | "bug" | "suggestion" | "question" | "free";

export type TreeAuthorRead = {
  id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
};

export type TreeRelatedCharacterRead = {
  id: string;
  name: string;
  handle: string | null;
  avatar_url: string | null;
};

export type TreePostSummary = {
  id: string;
  category: TreeCategory;
  title: string;
  body: string;
  author: TreeAuthorRead;
  related_character: TreeRelatedCharacterRead | null;
  comment_count: number;
  created_at: string;
  updated_at: string;
};

export type TreeCommentRead = {
  id: number;
  post_id: string;
  author: TreeAuthorRead;
  content: string;
  created_at: string;
};

export type TreePostDetail = TreePostSummary & {
  comments: TreeCommentRead[];
};

export type TreeFeedPage = {
  items: TreePostSummary[];
  next_cursor: string | null;
};

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  token?: string | null;
};

async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, token = getStoredToken(), ...rest } = options;
  const response = await fetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export function listTreePosts({
  category,
  query,
  cursor,
  limit = 10,
}: {
  category: TreeCategory;
  query?: string;
  cursor?: string | null;
  limit?: number;
}) {
  const params = new URLSearchParams({ category, limit: String(limit) });
  if (query?.trim()) params.set("q", query.trim());
  if (cursor) params.set("cursor", cursor);
  return apiRequest<TreeFeedPage>(`/tree/posts?${params.toString()}`, {
    token: null,
  });
}

export function createTreePost(data: {
  category: TreeCategory;
  title: string;
  body: string;
  related_character_id?: string | null;
}) {
  return apiRequest<TreePostDetail>("/tree/posts", {
    method: "POST",
    body: data,
  });
}

export function getTreePost(postId: string) {
  return apiRequest<TreePostDetail>(`/tree/posts/${postId}`, { token: null });
}

export function createTreeComment(postId: string, content: string) {
  return apiRequest<TreePostDetail>(`/tree/posts/${postId}/comments`, {
    method: "POST",
    body: { content },
  });
}
