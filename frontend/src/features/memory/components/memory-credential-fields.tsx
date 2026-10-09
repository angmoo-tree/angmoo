"use client";
import { apiRequest } from "@/lib/http/api-request";
import { CredentialFields, type SecretMetadata, type SecretWrite } from "@/components/ui/credential-fields";
import { GENERATION_PROFILES } from "@/config/generation-profiles";
import { useUiText } from "@/hooks/use-ui-text";

export function MemoryCredentialFields({ worldId, subjectId, purpose, onMetadata, onSaved, onDirtyChange, initialMetadata }: {
  worldId: string; subjectId: string; purpose: "consolidation" | "embedding"; onMetadata?: (value: SecretMetadata) => void; onDirtyChange?: (value: boolean) => void;
  initialMetadata?: SecretMetadata; onSaved?: (value: SecretMetadata) => void;
}) {
  const t = useUiText("memory");
  const path = `/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(subjectId)}/credentials/${purpose}`;
  const profiles = purpose === "embedding" ? [{ provider: "google", model: "gemini-embedding-2", thinking_level: null, label: "Gemini Embedding 2" }] :
    GENERATION_PROFILES.map(p => ({ provider: "google", model: p.model, thinking_level: p.thinking, label: p.label }));
  return <CredentialFields scopeKey={`${worldId}:${subjectId}:${purpose}`} profiles={profiles} onMetadata={onMetadata} onSaved={onSaved} initialMetadata={initialMetadata} onDirtyChange={onDirtyChange}
    read={signal => apiRequest<SecretMetadata>(path, { signal })}
    save={({ label: _label, ...data }: SecretWrite, signal) => { void _label; return apiRequest<SecretMetadata>(path, { method: "PUT", signal, body: data }); }}
    remove={(expected_revision, signal) => apiRequest<SecretMetadata>(path, { method: "DELETE", signal, body: { expected_revision } })}
    text={{ model: t(purpose === "embedding" ? "임베딩 모델" : "관계 정리 모델"), key: t("새 API key"), stored: t("API key 저장됨"), missing: t("API key 없음"), save: t("키·모델 저장"), remove: t("저장된 key 삭제"), confirm: t("이 용도의 API key를 삭제할까요?"), failed: t("저장하지 못했어요. 최신 설정을 확인해 주세요."), saved: t("설정을 저장했어요."), keep: t("비워 두면 저장된 키를 유지해요."), unsupported: t("현재 저장된 모델") }} />;
}
