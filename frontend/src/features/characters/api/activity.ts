import { apiRequest } from "@/lib/http/community-request";
import type { CharacterActivityRead } from "@/features/characters/types/activity";
import type { CharacterStateRead } from "@/features/characters/types/character";

export function getCharacterActivity(characterId: string) {
  return apiRequest<CharacterActivityRead>(`/characters/${characterId}/activity`);
}

export function saveCharacterState(
  characterId: string,
  data: {
    mood: string;
    summary: string;
    memory_note: string;
  },
) {
  return apiRequest<CharacterStateRead>(`/characters/${characterId}/state`, {
    method: "POST",
    body: data,
  });
}
