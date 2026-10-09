"use client";

import { useCallback } from "react";
import { apiRequest } from "@/lib/http/api-request";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import type { SecretMetadata } from "@/components/ui/credential-fields";
import { getMemoryEmbeddingSetting } from "../api/memory-client";
import type { MemoryEmbeddingSetting } from "../types/memory-embedding-contract";

export function useSavedEmbedding(worldId: string, subjectId: string, enabled: boolean, busy: boolean) {
  const read = useCallback(async (signal: AbortSignal) => {
    const [setting, credential] = await Promise.all([
      getMemoryEmbeddingSetting(worldId, subjectId, signal),
      apiRequest<SecretMetadata>(`/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(subjectId)}/credentials/embedding`, { signal }),
    ]);
    if (setting.scope.world_id !== worldId || setting.scope.subject_world_character_id !== subjectId ||
        setting.provider !== credential.provider || setting.model !== credential.model || (setting.enabled && setting.ready && !credential.has_key)) {
      throw new Error("memory_embedding_scope_or_key_changed");
    }
    return { setting, credential };
  }, [worldId, subjectId]);
  const refreshAt = useCallback((value: { setting: MemoryEmbeddingSetting }) => value.setting.enabled && !busy ? Date.now() + 5000 : null, [busy]);
  const state = useActiveScopedRead({ scopeKey: `${worldId}:${subjectId}:embedding`, active: enabled && Boolean(worldId && subjectId), read, refreshAt });
  return { ...state, saved: state.data?.setting ?? null, credential: state.data?.credential ?? null };
}

export type SavedEmbeddingController = ReturnType<typeof useSavedEmbedding>;

export function embeddingStorageNotice(state: SavedEmbeddingController): string {
  if (state.error) return "임베딩 설정 상태를 확인하지 못했어요.";
  if (state.loading || !state.saved || !state.credential) return "임베딩 설정 확인 중";
  if (state.saved.enabled && state.credential.has_key && !state.saved.ready) return "임베딩 설정 상태를 확인하지 못했어요.";
  return state.saved.enabled && state.saved.ready && state.credential.has_key
    ? "기억을 저장한 뒤 의미 검색 자료도 순서대로 준비해요."
    : "기억과 근거는 저장하고, 키워드 검색 자료만 준비해요.";
}
