import { apiRequest } from "@/features/social/api/request";
import type { PostDetail } from "@/features/social/types/community";

export function createCommunityPost(data: {
  title: string;
  body: string;
  author_character_id?: string;
}) {
  return apiRequest<PostDetail>("/posts", {
    method: "POST",
    body: data,
  });
}

export function likeCommunityPost(postId: string, characterId: string) {
  return apiRequest<PostDetail>(`/posts/${postId}/likes`, {
    method: "POST",
    body: { character_id: characterId },
  });
}
