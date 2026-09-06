import type { WorldCharacterSocialProfileTab } from "@/features/social/types/world-character-social-profile-contract";


export function parseWorldCharacterSocialProfileTab(
  value: string | null | undefined,
): WorldCharacterSocialProfileTab {
  return value === "replies" || value === "likes" ? value : "posts";
}
